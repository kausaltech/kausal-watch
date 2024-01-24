from __future__ import annotations
import typing

import json
import logging
from dal import autocomplete, forward as dal_forward
from django.contrib.admin.utils import quote
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Model
from django.urls import path, re_path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic.detail import SingleObjectMixin
from modelcluster.forms import childformset_factory
from typing import Iterable, Type
from wagtail.admin.panels import (
    FieldPanel, InlinePanel, MultiFieldPanel, ObjectList, Panel
)
from wagtail.admin.forms.models import WagtailAdminModelForm, formfield_for_dbfield
from wagtail.admin.widgets import AdminAutoHeightTextInput
from wagtail.permissions import ModelPermissionPolicy
from wagtail.snippets.action_menu import SnippetActionMenu
from wagtail.snippets.views.snippets import (
    CollectWorkflowActionDataView, ConfirmWorkflowCancellationView, UnpublishView, UsageView,
)
from wagtail_modeladmin.options import ModelAdminMenuItem
from wagtail_modeladmin.views import IndexView

from admin_site.wagtail import (
    AplansEditView, AdminOnlyPanel, AplansButtonHelper, AplansCreateView, AplansModelAdmin, AplansTabbedInterface,
    CondensedInlinePanel, CustomizableBuiltInFieldPanel, CustomizableBuiltInPlanFilteredFieldPanel,
    PlanFilteredFieldPanel, PlanRelatedPermissionHelper, insert_model_translation_panels, get_translation_tabs
)
from actions.chooser import ActionChooser
from admin_site.utils import FieldLabelRenderer
from aplans.extensions import modeladmin_register
from aplans.context_vars import ctx_instance, ctx_request
from aplans.types import WatchAdminRequest
from aplans.utils import naturaltime
from aplans.wagtail_utils import _get_category_fields
from orgs.models import Organization
from people.chooser import PersonChooser
from people.models import Person

from .action_admin_mixins import SnippetsEditViewCompatibilityMixin
from .models.action import Action, ActionContactPerson, ActionResponsibleParty, ActionTask, ModelWithRole
from reports.views import MarkActionAsCompleteView

if typing.TYPE_CHECKING:
    from users.models import User

logger = logging.getLogger(__name__)


class ReadOnlyInlinePanel(Panel):
    """Variant of InlinePanel where no form inputs are output."""
    def __init__(self, relation_name=None, *args, **kwargs):
        self.relation_name = relation_name
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        """
        Return a dictionary of keyword arguments that can be used to create a clone of this panel definition.
        """
        result = super().clone_kwargs()
        result['relation_name'] = self.relation_name
        return result

    class BoundPanel(Panel.BoundPanel):
        template_name = "aplans/panels/read_only_inline_panel.html"

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            relation_name = self.panel.relation_name
            context['items'] = [
                {
                    'label': el.get_label() if hasattr(el, 'get_label') else '',
                    'value': el.get_value() if hasattr(el, 'get_value') else str(el)
                }
                for el in getattr(self.instance, relation_name).all()
            ]
            return context


class ActionPermissionHelper(PlanRelatedPermissionHelper):
    def get_plans(self, obj):
        return [obj.plan]

    def user_can_edit_obj(self, user, obj):
        if not super().user_can_edit_obj(user, obj):
            return False

        return user.can_modify_action(obj)

    def user_can_delete_obj(self, user, obj):
        if not super().user_can_delete_obj(user, obj):
            return False

        if not user.can_modify_action(obj):
            return False

        plan = obj.plan
        if plan.actions_locked:
            return False

        return user.is_general_admin_for_plan(plan)

    def user_can_create(self, user: User):
        if not super().user_can_create(user):
            return False

        plan = user.get_active_admin_plan()
        return user.can_create_action(plan)


MODELS_WITH_ROLES: list[tuple[Type[ModelWithRole], str, Type[Model], str]] = [
    (ActionContactPerson, 'contact_persons',
     Person, 'person'),
    (ActionResponsibleParty, 'responsible_parties',
     Organization, 'organization')
]


class ActionAdminForm(WagtailAdminModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # There is a corresponding formset for a role if and only if we can edit contact persons of that role.
        for cls, relation_name, __, __ in MODELS_WITH_ROLES:
            for role in cls.get_roles():
                # For some models, the role can be blank
                # OMG, we're really hacking this so that a formset is called, e.g., `responsible_parties_None`...
                formset = self.formsets.get(f'{relation_name}_{role}')
                if formset:
                    formset.queryset = formset.queryset.filter(role=role)

    def clean_identifier(self):
        # Since we hide the plan in the form, `validate_unique()` will be called with `exclude` containing `plan`, in
        # which case the unique_together constraints of Action will not be checked. We do it manually here.
        identifier = self.cleaned_data['identifier']
        plan = self.instance.plan
        if Action.objects.filter(plan=plan, identifier=identifier).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("There is already an action with this identifier."))
        return identifier

    def get_related_objects_with_role(
            self, _cls: Type[ModelWithRole], role: str,
            relation_name: str, wrapped_cls: Type[Model], wrapped_object_attr: str
    ) -> typing.Iterable[Model]:
        formset = self.formsets.get(f'{relation_name}_{role}')
        # There is a corresponding formset for a role if and only if we can edit the relations of that role.
        if formset:
            if not formset.is_valid():
                return []  # Help! But apparently if the formset is invalid, there won't be `cleaned_data` in it!?
            return [data[wrapped_object_attr] for data in formset.cleaned_data if not data['DELETE']]
        obj_ids = getattr(self.instance, relation_name).filter(role=role).values_list(wrapped_object_attr, flat=True)
        return wrapped_cls.objects.filter(id__in=obj_ids)

    def _validate_unique_relations_with_roles(
            self, _cls: Type[ModelWithRole], relation_name: str, wrapped_object_cls: Type[Model], wrapped_object_attr: str
    ):
        seen_related_objects = set()
        for role in _cls.get_roles():
            if role is None:
                role = 'None'
            for obj in self.get_related_objects_with_role(
                _cls, role, relation_name, wrapped_object_cls, wrapped_object_attr
            ):
                if obj.pk in seen_related_objects:
                    raise ValidationError(
                        _("%s is listed multiple times in the action.") % obj
                    )
                seen_related_objects.add(obj.pk)

    def clean(self):
        for _cls, relation_name, wrapped_object_cls, wrapped_object_attr in MODELS_WITH_ROLES:
            self._validate_unique_relations_with_roles(_cls, relation_name, wrapped_object_cls, wrapped_object_attr)
            # Persons can only have at most one role as a contact person.
            # Organizations can only have at most one role as a responsible party

    def save(self, commit=True):
        if hasattr(self.instance, 'updated_at'):
            self.instance.updated_at = timezone.now()

        for _cls, relation_name, __, __ in MODELS_WITH_ROLES:
            formsets = {}
            # There is a corresponding formset for a role if and only if we can edit objects of that role.
            for role in _cls.get_roles():
                formset = self.formsets.pop(f'{relation_name}_{role}', None)
                if formset:
                    formsets[role] = formset
            manager = getattr(self.instance, relation_name)
            original_objects = manager.get_object_list().copy()
            obj: Action = super().save(commit)
            self.save_related_objects_with_role(manager, formsets, original_objects, commit)

        # Update categories
        plan = obj.plan
        for field_name, field in _get_category_fields(plan, Action, obj).items():
            field_data = self.cleaned_data.get(field_name)
            if field_data is None:
                continue
            cat_type = field.category_type
            obj.set_categories(cat_type, field_data)

        user = self._user
        # If we are serializing a draft (which happens when `commit` is false), we should include all attributes, i.e.,
        # also the non-editable ones. If we are saving a model instance, we only save the editable attributes.
        if commit:
            attribute_types = obj.get_editable_attribute_types(user)
        else:
            attribute_types = obj.get_visible_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.set_attributes(obj, self.cleaned_data, commit=commit)
        return obj

    def save_related_objects_with_role(self, manager, formsets, original_objects, commit=True):
        """Saves the related objects from the given role-specific formsets.

        For contact persons: If the plan does not distinguish contact persons by role, then there are no role-specific formsets and the
        contact persons (in the formset `contact_persons`) are saved in `super().save()`.
        """
        saved_objects = []  # but not yet committed
        deleted_objects = []
        order = 0
        for role, formset in formsets.items():
            saved_instances = formset.save(commit=False)
            for instance in saved_instances:
                if role is None:
                    instance.role = None
                else:
                    instance.role = str(role)
            # Each call of `formset.save()` changes the object list in the manager. We reset it to the original state,
            # and after all formsets have been processed, we'll manually set it to all objects from all formsets.
            manager.set(original_objects)
            saved_objects += saved_instances
            deleted_objects += formset.deleted_objects

            # Since we used `formset.save(commit=False)`, we won't touch the database, but the deferring related manager
            # will now have the wrong data because `BaseChildFormSet.save()` removes `no_id_instances` from it. Let's
            # not care about that and be happy with the saved instances we got as the return value of
            # `BaseChildFormSet.save()`. We have to be careful not to call the manager's `commit()` method as this would
            # remove items that are not in the current formset even though they are in a different one.

            # Fix order (see modelcluster's forms.py:105)
            # FIXME: When an instance changes order but is otherwise unchanged, the order set here will be ignored
            for i, form in enumerate(formset.ordered_forms):
                assert form.instance.order == i  # I guess?
                form.instance.order = order
                order += 1

        # Remove `no_id_instances` like in `BaseChildFormSet.save()`; otherwise, with a draft action that has an
        # ModelWithRole without an `id`, you could remove the form for that draft ModelWithRole and but
        # we'd still try to create an ModelWithRole instance.
        no_id_instances = [obj for obj in manager.all() if obj.pk is None]
        if no_id_instances:
            manager.remove(*no_id_instances)

        # Update object list of manager like BaseChildFormSet.save() does
        manager.add(*saved_objects)
        manager.remove(*deleted_objects)

        # The formsets have only been called with commit=False so far, so if we really should commit, we need to save
        # the instances with commit=True.
        if commit:
            manager.commit()


class ModelWithRoleInlinePanel(InlinePanel):
    @staticmethod
    def create_for_model_class(_cls: Type[ModelWithRole], *args, **kwargs):
        if _cls == ActionResponsibleParty:
            return ResponsiblePartiesInlinePanel(*args, **kwargs)
        if _cls == ActionContactPerson:
            return ContactPersonsInlinePanel(*args, **kwargs)

    def __init__(self, filter_by_role: bool, role: ModelWithRole.Role | None = None, *args, **kwargs):
        """If `filter_by_role` is false, we show all instances in this panel, otherwise only the ones with the given
        role. (`None` is a possible role for ActionResponsibleParty.)

        For the latter to work, make sure that your form contains formsets `contact_persons_<role>` (or equivalent for
        other models) whose querysets are filtered accordingly.
        """
        self.filter_by_role = filter_by_role
        self.role = role
        kwargs.setdefault('panels', self.get_panels())
        if filter_by_role:
            kwargs['relation_name'] = self.get_relation_name(role=role)
            if role:
                heading = role.label
            else:
                heading = _('Unspecified')
            kwargs.setdefault('heading', heading)
        else:
            kwargs['relation_name'] = self.get_relation_name()
            kwargs.setdefault('heading', self.get_heading())
        super().__init__(*args, **kwargs)

    def get_base_relation_name(self) -> str:
        raise NotImplementedError

    def get_panels(self) -> list:
        raise NotImplementedError

    def get_heading(self) -> str:
        raise NotImplementedError

    def get_relation_name(self, role: ModelWithRole.Role | None = None) -> str:
        base = self.get_base_relation_name()
        if not self.filter_by_role:
            return base
        return f'{base}_{role}'

    def clone_kwargs(self):
        result = super().clone_kwargs()
        result['filter_by_role'] = self.filter_by_role
        result['role'] = self.role
        return result

    def on_model_bound(self):
        assert ((self.filter_by_role and self.relation_name == self.get_relation_name(self.role))
                or self.relation_name == self.get_relation_name())
        # In either case, we set the DB field to `contact_persons` (or similarly for other models). We rely on the
        # queryset for `contact_persons_{role}` being filtered accordingly due to `ActionAdminForm.__init__()`.
        # The code below could be simplified, but let's keep it like this to resemble InlinePanel.on_model_bound()`.
        assert self.model == Action
        manager = getattr(self.model, self.get_base_relation_name())
        self.db_field = manager.rel


# FIXME: Duplicates stuff from ReadOnlyInlinePanel
class ModelWithRoleReadOnlyInlinePanel(Panel):
    def __init__(
            self,
            relation_name: str | None = None,
            filter_by_role: bool = False,
            role: ModelWithRole.Role | None = None,
            *args, **kwargs
        ):
        self.filter_by_role = filter_by_role
        self.role = role
        self.relation_name = relation_name
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        result = super().clone_kwargs()
        result['filter_by_role'] = self.filter_by_role
        result['role'] = self.role
        result['relation_name'] = self.relation_name
        return result

    class BoundPanel(Panel.BoundPanel):
        template_name = "aplans/panels/read_only_inline_panel.html"

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            manager = getattr(self.instance, self.panel.relation_name)
            if self.panel.filter_by_role:
                qs = manager.filter(role=self.panel.role)
            else:
                qs = manager.all()
            context['items'] = [
                {
                    'label': el.get_label() if hasattr(el, 'get_label') else '',
                    'value': el.get_value() if hasattr(el, 'get_value') else str(el)
                }
                for el in qs
            ]
            return context


class ResponsiblePartiesInlinePanel(ModelWithRoleInlinePanel):
    def get_heading(self):
        return _('Responsible parties')

    def get_base_relation_name(self):
        return 'responsible_parties'

    def get_panels(self):
        panels = [
            FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        ]
        if not self.filter_by_role:
            panels.append(FieldPanel('role'))
        panels.append(FieldPanel('specifier'))
        return panels


class ContactPersonsInlinePanel(ModelWithRoleInlinePanel):
    def get_heading(self):
        return _('Contact persons')

    def get_base_relation_name(self):
        return 'contact_persons'

    def get_panels(self):
        return [
            FieldPanel('person', widget=PersonChooser),
            FieldPanel('primary_contact')
        ]


class RelatedModelWithRolePanel(MultiFieldPanel):
    def __init__(
        self,
        action: Action,
        relation_name: str,
        _cls: Type[ModelWithRole],
        editable_roles: Iterable[ModelWithRole.Role | None] | None = None,
        *args, **kwargs
    ):
        """Display inline panels for contact persons, optionally separated by roles.

        If `editable_roles` is None, a single inline panel will be shown for all contact persons without distuinguishing
        them by roles.

        Otherwise an inline panel will be included for each role, no matter if it is included in `editable_roles`. The
        type of the panel will differ, however, depending on whether contact persons with that role can be edited.
        """
        self.action = action
        self.relation_name = relation_name
        self._cls = _cls
        self.editable_roles = editable_roles
        children = []
        assert _cls  # TODO: Didn't really check when or if it can actually be None
        if editable_roles is None:
            children.append(ModelWithRoleInlinePanel.create_for_model_class(_cls, filter_by_role=False))
        else:
            for role in _cls.get_roles():
                # Only show panel for "unspecified" role if there are instances with an unspecified role
                # https://github.com/kausaltech/kausal-watch-private/pull/111#issuecomment-1896291423
                if role is None and not getattr(action, relation_name).filter(role__isnull=True).exists():
                    continue
                if role in editable_roles:
                    panel = ModelWithRoleInlinePanel.create_for_model_class(_cls, filter_by_role=True, role=role)
                else:
                    panel = ModelWithRoleReadOnlyInlinePanel(relation_name, filter_by_role=True, role=role)
                children.append(panel)
        super().__init__(children=children, *args, **kwargs)

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        # children are statically set in __init__
        kwargs.pop('children')
        kwargs['action'] = self.action
        kwargs['relation_name'] = self.relation_name
        kwargs['_cls'] = self._cls
        kwargs['editable_roles'] = self.editable_roles
        return kwargs


class ActionEditHandler(AplansTabbedInterface):
    def __init__(self, *args, serialized_attributes=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.serialized_attributes = serialized_attributes

    def clone_kwargs(self):
        result = super().clone_kwargs()
        result['serialized_attributes'] = self.serialized_attributes
        return result

    def get_form_class(self):
        from admin_site.models import BuiltInFieldCustomization

        request = ctx_request.get()
        instance = ctx_instance.get()
        assert isinstance(instance, Action)
        user = request.user
        plan = request.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            cat_fields = _get_category_fields(plan, Action, instance, with_initial=True)
        else:
            cat_fields = {}

        if instance is not None:
            attribute_types = instance.get_visible_attribute_types(user)
            attribute_fields = {field.name: field.django_field
                                for attribute_type in attribute_types
                                for field in attribute_type.get_form_fields(
                                        user, plan, instance, serialized_attributes=self.serialized_attributes
                                )}
        else:
            attribute_fields = {}

        self.base_form_class = type(
            'ActionAdminForm',
            (ActionAdminForm,),
            {**cat_fields, **attribute_fields, '_user': user}
        )

        form_class = super().get_form_class()

        if (not plan.features.has_action_identifiers or plan.actions_locked) and 'identifier' in form_class.base_fields:
            # 'identifier' may not be in the fields due to built-in field customizations
            form_class.base_fields['identifier'].disabled = True
            form_class.base_fields['identifier'].required = False

        if plan.actions_locked and 'official_name' in form_class.base_fields:
            # 'official_name' may not be in the fields if the plan has official names disabled or due to built-in field
            # customizations
            form_class.base_fields['official_name'].disabled = True
            form_class.base_fields['official_name'].required = False

        # Disable / remove built-in fields that are not editable / visible due to customization
        customizations_qs = BuiltInFieldCustomization.objects.filter(
            plan=plan,
            content_type=ContentType.objects.get_for_model(Action),
        )
        customizations: dict[str, BuiltInFieldCustomization] = {c.field_name: c for c in customizations_qs}
        for field_name in list(form_class.base_fields.keys()):
            customization = customizations.get(field_name)
            if customization:
                if not customization.is_instance_visible_for(user, plan, instance):
                    del form_class.base_fields[field_name]
                    continue
                if not customization.is_instance_editable_by(user, plan, instance):
                    form_class.base_fields[field_name].disabled = True
                    form_class.base_fields[field_name].required = False

        if not user.is_general_admin_for_plan(plan):
            for panel in list(self.children):
                if not isinstance(panel, AdminOnlyPanel):
                    continue
                for child in panel.children:
                    if isinstance(child, FieldPanel):
                        del form_class.base_fields[child.field_name]
                    elif isinstance(child, InlinePanel):
                        del form_class.formsets[child.relation_name]
                    else:
                        raise Exception('Invalid child panel: %s' % child)

        field = form_class.base_fields.get('impact')
        if field is not None:
            field.queryset = field.queryset.filter(plan=plan)

        field = form_class.base_fields.get('status')
        if field is not None:
            field.queryset = field.queryset.filter(plan=plan)

        # Manually add a formset for each contact person role whose contact persons we may edit.
        # There is a corresponding formset in the form options if and only if we can edit contact persons of a
        # certain role.
        for role in ActionContactPerson.get_roles():
            form_options = self.get_form_options()
            formset_name = f'contact_persons_{role}'
            formset_options = form_options['formsets'].get(formset_name)
            if formset_options:
                kwargs = {
                    'extra': 0,
                    'fk_name': 'action',
                    'form': WagtailAdminModelForm,
                    'formfield_callback': formfield_for_dbfield,
                    **form_options['formsets'][formset_name],
                }
                form_class.formsets[formset_name] = childformset_factory(Action, ActionContactPerson, **kwargs)

        for role in ActionResponsibleParty.get_roles():
            form_options = self.get_form_options()
            formset_name = f'responsible_parties_{role}'
            formset_options = form_options['formsets'].get(formset_name)
            if formset_options:
                kwargs = {
                    'extra': 0,
                    'fk_name': 'action',
                    'form': WagtailAdminModelForm,
                    'formfield_callback': formfield_for_dbfield,
                    **form_options['formsets'][formset_name],
                }
                form_class.formsets[formset_name] = childformset_factory(Action, ActionResponsibleParty, **kwargs)
        return form_class


class ActionCreateView(AplansCreateView):
    instance: Action

    def initialize_instance(self, request):
        plan = request.user.get_active_admin_plan()
        assert self.instance.pk is None
        assert not hasattr(self.instance, 'plan')
        self.instance.plan = plan
        if not plan.features.has_action_identifiers:
            assert not self.instance.identifier
            self.instance.generate_identifier()
        if plan.features.has_action_primary_orgs:
            assert self.instance.primary_org is None
            person = request.user.get_corresponding_person()
            if person is not None:
                available_orgs = Organization.objects.available_for_plan(plan)
                default_org = available_orgs.filter(id=person.organization_id).first()
                self.instance.primary_org = default_org


class ActionIndexView(IndexView):
    request: WatchAdminRequest

    def get_page_title(self):
        plan = self.request.user.get_active_admin_plan()
        return plan.general_content.get_action_term_display_plural()


class ActionMenuItem(ModelAdminMenuItem):
    def render_component(self, request):
        link_menu_item = super().render_component(request)
        plan = request.user.get_active_admin_plan()
        # Change label to the configured term for "Action"
        link_menu_item.label = plan.general_content.get_action_term_display_plural()
        return link_menu_item


class ActionButtonHelper(AplansButtonHelper):
    mark_as_complete_button_classnames: list[str] = []

    def mark_as_complete_button(self, action_pk, report, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.mark_as_complete_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('mark_action_as_complete', quote(action_pk), quote(report.pk)),
            'label': _("Mark as complete for report %s") % report.name,
            'classname': cn,
            'title': _("Mark this action as complete for the report %s") % str(report),
        }

    def undo_marking_as_complete_button(self, action_pk, report, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.mark_as_complete_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('undo_marking_action_as_complete', quote(action_pk), quote(report.pk)),
            'label': _("Undo marking as complete for report %s") % report.name,
            'classname': cn,
            'title': _("Undo marking this action as complete for the report %s") % str(report),
        }

    def get_buttons_for_obj(self, obj: Action, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)
        if not self.permission_helper.user_can_edit_obj(self.request.user, obj):
            return buttons

        latest_reports = self.request.admin_cache.latest_reports
        # For each report type, display one button for the latest report of that type
        for latest_report in latest_reports:
            if latest_report.is_complete:
                continue
            if obj.is_complete_for_report(latest_report):
                buttons.append(self.undo_marking_as_complete_button(obj.pk, latest_report, **kwargs))
            else:
                buttons.append(self.mark_as_complete_button(obj.pk, latest_report, **kwargs))
        return buttons


class ActionEditView(SnippetsEditViewCompatibilityMixin, SingleObjectMixin, AplansEditView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.instance.plan.features.enable_moderation_workflow:
            context['action_menu'] = SnippetActionMenu(
                self.request,
                view='edit',
                model=self.model,
                instance=self.instance,
                locked_for_user=self.locked_for_user,
            )
        return context

    def get_description(self):
        action = self.instance
        primary_action_classification = action.plan.primary_action_classification
        if primary_action_classification is None:
            return ''
        category = action.categories.filter(type=primary_action_classification)
        if not category:
            return ''
        category = category.first()
        crumb = [category]
        parent = category.parent
        while parent is not None:
            crumb.append(parent)
            parent = parent.parent
        return " / ".join([str(c) for c in reversed(crumb)])

    def get_edit_handler(self):
        # We need to inject this view's instance to be accessible to the edit handler
        # since it needs to know whether we are editing a draft or a live
        # object (there is a difference in how the form panels are constructed)
        edit_handler = self.model_admin.get_edit_handler(instance_being_edited=self.object)
        return edit_handler.bind_to_model(self.model_admin.model)


@modeladmin_register
class ActionAdmin(AplansModelAdmin):
    model = Action
    create_view_class = ActionCreateView
    index_view_class = ActionIndexView
    edit_view_class = ActionEditView
    menu_icon = 'kausal-action'
    menu_order = 10
    list_display = ('identifier', 'name_link')
    list_display_add_buttons = 'name_link'
    search_fields = ('identifier', 'name')
    permission_helper_class = ActionPermissionHelper
    button_helper_class = ActionButtonHelper
    index_order_field = 'order'

    ordering = ['order']

    usage_view_class = UsageView
    unpublish_view_class = UnpublishView
    collect_workflow_action_data_view_class = CollectWorkflowActionDataView
    confirm_workflow_cancellation_view_class = ConfirmWorkflowCancellationView

    basic_panels = [
        CustomizableBuiltInFieldPanel('identifier'),
        CustomizableBuiltInFieldPanel('official_name'),
        CustomizableBuiltInFieldPanel('name'),
        CustomizableBuiltInFieldPanel('primary_org', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        CustomizableBuiltInFieldPanel('lead_paragraph'),
        CustomizableBuiltInFieldPanel('description'),
    ]
    basic_related_panels = [
        CustomizableBuiltInFieldPanel('image')
    ]
    basic_related_panels_general_admin = [
        CustomizableBuiltInFieldPanel(
            'related_actions',
            widget=autocomplete.ModelSelect2Multiple(
                url='action-autocomplete',
                forward=(
                    dal_forward.Const(True, 'related_plans'),
                )
            )
        ),
        CustomizableBuiltInFieldPanel('merged_with', widget=ActionChooser),
        CustomizableBuiltInFieldPanel('visibility'),
    ]

    progress_panels = [
        CustomizableBuiltInPlanFilteredFieldPanel('implementation_phase'),
        CustomizableBuiltInPlanFilteredFieldPanel('status'),
        CustomizableBuiltInFieldPanel('manual_status'),
        CustomizableBuiltInFieldPanel('manual_status_reason'),
        CustomizableBuiltInFieldPanel('schedule_continuous'),
        CustomizableBuiltInFieldPanel('start_date'),
        CustomizableBuiltInFieldPanel('end_date'),
    ]

    task_panels = [
        FieldPanel('name'),
        FieldPanel('due_at'),
        FieldPanel('state'),
        FieldPanel('completed_at'),
        FieldPanel('comment'),
    ]

    task_header_from_js = '''
        function getHeader(task) {
            var f = task.fields;
            var out = '';
            if (!f.name) {
                return '';
            }
            var stateMap = %(state_map)s;
            if (f.name && f.name.length > 80) {
                out = f.name.slice(0, 80) + '...';
            } else {
                out = f.name;
            }
            var stateStr = stateMap[f.state];
            if (f.state != 'completed' && f.state != 'cancelled' && f.due_at) {
                stateStr += ', DL: ' + f.due_at;
            }
            out += ' <span class="action-task-header-state">(' + stateStr + ')</span>'
            return out;
        }
        getHeader(form);
    '''

    def register_with_wagtail(self):
        super().register_with_wagtail()

        class FakeSnippetViewSet:
            def __init__(self, modeladmin):
                self.modeladmin = modeladmin

            def get_url_name(self, view_name):
                return self.modeladmin.get_url_name(view_name)

            def get_menu_item_is_registered(self):
                return False

        Action.snippet_viewset = FakeSnippetViewSet(self)

        from wagtail.snippets.models import SNIPPET_MODELS
        SNIPPET_MODELS.append(Action)
        SNIPPET_MODELS.sort(key=lambda x: x._meta.verbose_name)

    def get_url_name(self, view_name):
        if view_name == 'list':
            view_name = 'index'
        return self.url_helper.get_action_url_name(view_name)

    def updated_at_delta(self, obj):
        if not obj.updated_at:
            return None
        now = obj.plan.now_in_local_timezone()
        delta = now - obj.updated_at
        return naturaltime(delta)
    updated_at_delta.short_description = _('Last updated')

    def get_list_display(self, request: WatchAdminRequest):
        cached_list_display = getattr(request, '_action_admin_list_display', None)
        if cached_list_display:
            return cached_list_display

        def name_link(obj):
            from django.utils.html import format_html

            if self.permission_helper.user_can_edit_obj(request.user, obj):
                url = self.url_helper.get_action_url('edit', obj.pk)
                return format_html('<a href="{}">{}</a>', url, obj.name)
            else:
                return obj.name
        name_link.short_description = _('Name')
        self.name_link = name_link

        plan = request.user.get_active_admin_plan()

        list_display = ['name_link']
        if plan.features.has_action_identifiers:
            list_display.insert(0, 'identifier')
        if plan.features.has_action_primary_orgs:
            list_display.insert(0, 'primary_org')

        ct = plan.category_types.filter(identifier='action').first()
        if ct:
            def action_category(obj):
                return '; '.join([str(cat) for cat in obj.categories.all() if cat.type_id == ct.id])
            action_category.short_description = ct.name
            self.action_category = action_category
            list_display.append('action_category')

        list_display.append('updated_at_delta')

        """
        if not plan.actions_locked and request.user.is_general_admin_for_plan(plan):
            list_display.insert(0, 'index_order')
        """

        out = tuple(list_display)
        request._action_admin_list_display = out
        return out

    def get_task_header_formatter(self):
        states = {key: str(label) for key, label in list(ActionTask.STATES)}
        out = self.task_header_from_js % dict(state_map=json.dumps(states))
        return out

    def get_edit_handler(self, instance_being_edited: Action | None = None):
        request = ctx_request.get()
        instance: Action = ctx_instance.get()
        # TODO: find out how to include the relevant draftable mixin state
        # to the context instance so no separate instance_being_edited would
        # be needed.

        assert isinstance(instance, Action)
        plan = request.user.get_active_admin_plan()
        assert plan is not None

        render_field_label = FieldLabelRenderer(plan)

        task_panels = insert_model_translation_panels(ActionTask, self.task_panels, request, plan)
        serialized_attributes = instance_being_edited.get_serialized_attribute_data() if instance_being_edited else None
        attribute_panels = instance.get_attribute_panels(
            request.user,
            serialized_attributes=serialized_attributes
        )
        main_attribute_panels, reporting_attribute_panels, i18n_attribute_panels = attribute_panels

        all_tabs = []

        is_general_admin = request.user.is_general_admin_for_plan(plan)
        panels = list(self.basic_panels)
        for panel in list(panels):
            field_name = getattr(panel, 'field_name', None)
            if not field_name:
                continue
            if field_name == 'official_name' and not plan.features.has_action_official_name:
                panels.remove(panel)
            elif field_name == 'lead_paragraph' and not plan.features.has_action_lead_paragraph:
                panels.remove(panel)
            elif field_name == 'primary_org' and not plan.features.has_action_primary_orgs:
                panels.remove(panel)

        panels += main_attribute_panels

        if is_general_admin:
            cat_fields = _get_category_fields(instance.plan, Action, instance, with_initial=True)
            cat_panels = []
            for key, field in cat_fields.items():
                cat_panels.append(FieldPanel(key, heading=render_field_label(field.label, public=False)))
            if cat_panels:
                panels.append(MultiFieldPanel(cat_panels, heading=_('Categories')))

        for panel in self.basic_related_panels:
            panels.append(panel)

        panels.append(
            CondensedInlinePanel(
                'links',
                panels=[
                    FieldPanel('url'),
                    FieldPanel('title')
                ],
                heading=render_field_label(_('External links'), public=True),
            ),
        )

        if is_general_admin:
            panels += self.basic_related_panels_general_admin

            if plan.superseded_by:
                panels.append(FieldPanel('superseded_by', widget=autocomplete.ModelSelect2(
                    url='action-autocomplete',
                    forward=(
                        dal_forward.Const(plan.superseded_by.id, 'plan'),
                    )
                )))

        all_tabs.append(ObjectList(panels, heading=_('Basic information')))

        progress_panels = list(self.progress_panels)

        # If all of the action statuses are updated manually, remove the
        # manual status toggle.
        if plan.statuses_updated_manually:
            for panel in progress_panels:
                if panel.field_name == 'manual_status':
                    progress_panels.remove(panel)
                    break

        all_tabs.append(ObjectList(progress_panels, heading=_('Progress')))

        contact_persons_panels = self.get_contact_persons_panels(request, instance)
        all_tabs.append(ObjectList(
            contact_persons_panels,
            help_text=render_field_label('', public=plan.features.public_contact_persons), heading=_('Contact persons')
        ))

        responsible_parties_panels = self.get_responsible_parties_panels(request, instance)
        all_tabs.append(ObjectList(
            responsible_parties_panels, help_text=render_field_label('', public=True), heading=_('Responsible parties')))

        all_tabs += [
            ObjectList([
                CondensedInlinePanel(
                    'tasks',
                    panels=task_panels,
                )
            ], heading=plan.general_content.get_action_task_term_display_plural(),
               help_text=render_field_label('', public=True)),
        ]

        reporting_panels = reporting_attribute_panels
        help_panels_for_field = {}
        for snapshot in instance.get_snapshots():
            for field in snapshot.report.type.fields:
                help_panel = field.block.get_help_panel(field.value, snapshot)
                if help_panel:
                    help_panels_for_field.setdefault(field.id, []).append(help_panel)
        for help_panels in help_panels_for_field.values():
            reporting_panels += help_panels
        reporting_panels.append(
            FieldPanel(
                'internal_notes',
                heading=render_field_label(_('Internal notes'), public=False),
                widget=AdminAutoHeightTextInput(attrs=dict(rows=5))
            )
        )

        if is_general_admin:
            reporting_panels.append(
                FieldPanel(
                    'internal_admin_notes',
                    heading=render_field_label(_('Internal notes for plan administrators'), public=False),
                    widget=AdminAutoHeightTextInput(attrs=dict(rows=5))
                )
            )
            if plan.action_impacts.exists():
                reporting_panels.append(PlanFilteredFieldPanel('impact'))
            if plan.action_schedules.exists():
                reporting_panels.append(PlanFilteredFieldPanel('schedule'))

        all_tabs.append(ObjectList(reporting_panels, heading=_('Reporting')))

        i18n_tabs = get_translation_tabs(instance, request, extra_panels=i18n_attribute_panels)
        all_tabs += i18n_tabs

        return ActionEditHandler(
            all_tabs,
            serialized_attributes=serialized_attributes,
        )

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        if not request.user.is_general_admin_for_plan(plan):
            qs = qs.unmerged()
        qs = qs.filter(plan=plan)
        qs = qs.select_related('plan').prefetch_related('categories')
        return qs

    def get_menu_item(self, order=None):
        return ActionMenuItem(self, order or self.get_menu_order())

    def mark_action_as_complete_view(self, request, action_pk, report_pk):
        return MarkActionAsCompleteView.as_view(
            model_admin=self,
            action_pk=action_pk,
            report_pk=report_pk,
            complete=True,
        )(request)

    def undo_marking_action_as_complete_view(self, request, action_pk, report_pk):
        return MarkActionAsCompleteView.as_view(
            model_admin=self,
            action_pk=action_pk,
            report_pk=report_pk,
            complete=False,
        )(request)

    @property
    def permission_policy(self):
        return ModelPermissionPolicy(Action)

    @property
    def usage_view(self):
        return self.usage_view_class.as_view(
            model=self.model,
            # template_name=self.get_templates(
            #     "usage", fallback=self.usage_view_class.template_name
            # ),
            template_name=self.usage_view_class.template_name,
            # header_icon=self.icon,
            permission_policy=self.permission_policy,
            index_url_name=self.get_url_name("list"),
            edit_url_name=self.get_url_name("edit"),
        )

    @property
    def unpublish_view(self):
        return self.unpublish_view_class.as_view(
            model=self.model,
            # template_name=self.get_templates(
            #     "unpublish", fallback=self.unpublish_view_class.template_name
            # ),
            template_name=self.unpublish_view_class.template_name,
            # header_icon=self.icon,
            permission_policy=self.permission_policy,
            index_url_name=self.get_url_name("list"),
            edit_url_name=self.get_url_name("edit"),
            unpublish_url_name=self.get_url_name("unpublish"),
            usage_url_name=self.get_url_name("usage"),
        )

    @property
    def collect_workflow_action_data_view(self):
        return self.collect_workflow_action_data_view_class.as_view(
            model=self.model,
            redirect_url_name=self.get_url_name("edit"),
            submit_url_name=self.get_url_name("collect_workflow_action_data"),
        )

    @property
    def confirm_workflow_cancellation_view(self):
        return self.confirm_workflow_cancellation_view_class.as_view(model=self.model)

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        mark_as_complete_url = re_path(
            # self.url_helper.get_action_url_pattern('mark_action_as_complete'),
            r'^%s/%s/%s/(?P<action_pk>[-\w]+)/(?P<report_pk>[-\w]+)/$' % (
                self.opts.app_label,
                self.opts.model_name,
                'mark_action_as_complete',
            ),
            self.mark_action_as_complete_view,
            name=self.url_helper.get_action_url_name('mark_action_as_complete')
        )
        undo_marking_as_complete_url = re_path(
            # self.url_helper.get_action_url_pattern('undo_marking_action_as_complete'),
            r'^%s/%s/%s/(?P<action_pk>[-\w]+)/(?P<report_pk>[-\w]+)/$' % (
                self.opts.app_label,
                self.opts.model_name,
                'undo_marking_action_as_complete',
            ),
            self.undo_marking_action_as_complete_view,
            name=self.url_helper.get_action_url_name('undo_marking_action_as_complete')
        )
        snippet_view_routes = {
            'usage': '<str:pk>',
            'unpublish': '<str:pk>',
            'collect_workflow_action_data': '<str:pk>/<slug:action_name>/<int:task_state_id>',
            'confirm_workflow_cancellation': '<str:pk>',
        }
        snippet_view_urls = [
            path(
                f'{self.opts.app_label}/{self.opts.model_name}/{view_name}/{route}/',
                getattr(self, f'{view_name}_view'),
                name=self.url_helper.get_action_url_name(view_name)
            ) for view_name, route in snippet_view_routes.items()
        ]
        return urls + (
            mark_as_complete_url,
            undo_marking_as_complete_url,
            *snippet_view_urls,
        )

    def get_contact_persons_panels(self, request, instance: Action):
        plan = request.user.get_active_admin_plan()
        if plan.features.has_action_contact_person_roles:
            editable_contact_person_roles = request.user.get_editable_contact_person_roles(instance)
            return [
                RelatedModelWithRolePanel(
                    action=instance, relation_name='contact_persons', _cls=ActionContactPerson,
                    editable_roles=editable_contact_person_roles
                )]
        return [RelatedModelWithRolePanel(action=instance, relation_name='contact_persons', _cls=ActionContactPerson)]

    def get_responsible_parties_panels(self, request, instance: Action):
        plan = request.user.get_active_admin_plan()
        if plan.features.has_action_contact_person_roles:
            editable_responsible_party_roles = request.user.get_editable_responsible_party_roles(instance)
            return [
                RelatedModelWithRolePanel(
                    action=instance, relation_name='responsible_parties', _cls=ActionResponsibleParty,
                    editable_roles=editable_responsible_party_roles
            )]
        return [
            RelatedModelWithRolePanel(action=instance, relation_name='responsible_parties', _cls=ActionResponsibleParty)
        ]
