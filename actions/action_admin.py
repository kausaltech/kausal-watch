from __future__ import annotations
import typing

import json
import logging
from dal import autocomplete, forward as dal_forward
from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.urls import path, re_path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.generic.detail import SingleObjectMixin
from modelcluster.forms import childformset_factory
from typing import Iterable
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
    AplansEditView, AdminOnlyPanel, AplansButtonHelper, AplansCreateView, AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel,
    PlanFilteredFieldPanel, PlanRelatedPermissionHelper, insert_model_translation_panels,
    get_translation_tabs
)
from actions.chooser import ActionChooser
from aplans.extensions import modeladmin_register
from aplans.context_vars import ctx_instance, ctx_request
from aplans.types import WatchAdminRequest
from aplans.utils import naturaltime
from aplans.wagtail_utils import _get_category_fields
from orgs.models import Organization
from people.chooser import PersonChooser

from .action_admin_mixins import SnippetsEditViewCompatibilityMixin
from .models import Action, ActionContactPerson, ActionTask
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


class ActionAdminForm(WagtailAdminModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # There is a corresponding formset for a role if and only if we can edit contact persons of that role.
        for role in ActionContactPerson.Role:
            formset = self.formsets.get(f'contact_persons_{role}')
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

    def clean(self):
        # Persons can only have at most one role as a contact person.
        seen_contact_persons = set()
        # There is a corresponding formset for a role if and only if we can edit contact persons of that role.
        for role in ActionContactPerson.Role:
            formset = self.formsets.get(f'contact_persons_{role}')
            if not formset:
                continue
            for data in formset.cleaned_data:
                if not data['DELETE']:
                    person = data['person']
                    if person.id in seen_contact_persons:
                        raise ValidationError(
                            _("%s is listed multiple times as a contact person.") % person
                        )
                    seen_contact_persons.add(person.id)

    def save(self, commit=True):
        if hasattr(self.instance, 'updated_at'):
            self.instance.updated_at = timezone.now()

        contact_persons_formsets = {}
        # There is a corresponding formset for a role if and only if we can edit contact persons of that role.
        for role in ActionContactPerson.Role:
            formset = self.formsets.pop(f'contact_persons_{role}', None)
            if formset:
                contact_persons_formsets[role] = formset
        original_contact_persons = self.instance.contact_persons.get_object_list().copy()
        obj: Action = super().save(commit)
        self.save_contact_persons(contact_persons_formsets, original_contact_persons, commit)

        # Update categories
        plan = obj.plan
        for field_name, field in _get_category_fields(plan, Action, obj).items():
            field_data = self.cleaned_data.get(field_name)
            if field_data is None:
                continue
            cat_type = field.category_type
            obj.set_categories(cat_type, field_data)

        user = self._user
        attribute_types = obj.get_visible_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.set_attributes(obj, self.cleaned_data, commit=commit)
        return obj

    def save_contact_persons(self, contact_persons_formsets, original_contact_persons, commit=True):
        """Saves the contact persons from the given role-specific formsets.

        If the plan does not distinguish contact persons by role, then there are no role-specific formsets and the
        contact persons (in the formset `contact_persons`) are saved in `super().save()`.
        """
        manager = self.instance.contact_persons
        saved_contact_persons = []  # but not yet committed
        deleted_contact_persons = []
        order = 0
        for role, formset in contact_persons_formsets.items():
            saved_instances = formset.save(commit=False)
            for instance in saved_instances:
                instance.role = str(role)
            # Each call of `formset.save()` changes the object list in the manager. We reset it to the original state,
            # and after all formsets have been processed, we'll manually set it to all objects from all formsets.
            manager.set(original_contact_persons)
            saved_contact_persons += saved_instances
            deleted_contact_persons += formset.deleted_objects

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

        # Update object list of manager like BaseChildFormSet.save() does
        manager.add(*saved_contact_persons)
        manager.remove(*deleted_contact_persons)

        # The formsets have only been called with commit=False so far, so if we really should commit, we need to save
        # the instances with commit=True.
        if commit:
            manager.commit()


class ContactPersonsInlinePanel(InlinePanel):
    def __init__(self, role: ActionContactPerson.Role | None = None, *args, **kwargs):
        """If `role` is None, we show all contact persons in this panel, otherwise only the ones with that role.

        For the latter to work, make sure that your form contains formsets `contact_persons_<role>` whose querysets are
        filtered accordingly.
        """
        self.role = role
        kwargs.setdefault('panels', [
            FieldPanel('person', widget=PersonChooser),
            FieldPanel('primary_contact')
        ])
        if role:
            kwargs['relation_name'] = f'contact_persons_{role}'
            kwargs.setdefault('heading', role.label)
        else:
            kwargs['relation_name'] = 'contact_persons'
            kwargs.setdefault('heading', _('Contact persons'))
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        result = super().clone_kwargs()
        result['role'] = self.role
        return result

    def on_model_bound(self):
        assert ((self.role and self.relation_name == f'contact_persons_{self.role}')
                or self.relation_name == 'contact_persons')
        # In either case, we set the DB field to `contact_persons`. We rely on the queryset for `contact_persons_{role}`
        # being filtered accordingly due to `ActionAdminForm.__init__()`.
        # The code below could be simplified, but let's keep it like this to resemble InlinePanel.on_model_bound()`.
        assert self.model == Action
        manager = getattr(self.model, 'contact_persons')
        self.db_field = manager.rel


# FIXME: Duplicates stuff from ReadOnlyInlinePanel
class ContactPersonsReadOnlyInlinePanel(Panel):
    def __init__(self, role: ActionContactPerson.Role | None = None, *args, **kwargs):
        self.role = role
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        result = super().clone_kwargs()
        result['role'] = self.role
        return result

    class BoundPanel(Panel.BoundPanel):
        template_name = "aplans/panels/read_only_inline_panel.html"

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            role = self.panel.role
            if role:
                qs = self.instance.contact_persons.filter(role=role)
            else:
                qs = self.instance.contact_persons.all()
            context['items'] = [
                {
                    'label': el.get_label() if hasattr(el, 'get_label') else '',
                    'value': el.get_value() if hasattr(el, 'get_value') else str(el)
                }
                for el in qs
            ]
            return context


class ContactPersonsPanel(MultiFieldPanel):
    def __init__(self, *args, editable_roles: Iterable[ActionContactPerson.Role] | None = None, **kwargs):
        """Display inline panels for contact persons, optionally separated by roles.

        If `editable_roles` is None, a single inline panel will be shown for all contact persons without distuinguishing
        them by roles.

        Otherwise an inline panel will be included for each role, no matter if it is included in `editable_roles`. The
        type of the panel will differ, however, depending on whether contact persons with that role can be edited.
        """
        self.editable_roles = editable_roles
        children = []
        if editable_roles is None:
            children.append(ContactPersonsInlinePanel())
        else:
            for role in ActionContactPerson.Role:
                if role in editable_roles:
                    panel = ContactPersonsInlinePanel(role)
                else:
                    panel = ContactPersonsReadOnlyInlinePanel(role)
                children.append(panel)
        super().__init__(children=children, *args, **kwargs)

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        # children are statically set in __init__
        kwargs.pop('children')
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
        request = ctx_request.get()
        instance = ctx_instance.get()
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

        if not plan.features.has_action_identifiers or plan.actions_locked:
            form_class.base_fields['identifier'].disabled = True
            form_class.base_fields['identifier'].required = False

        if plan.actions_locked and 'official_name' in form_class.base_fields:
            # 'official_name' may not be in the fields if the plan has official names disabled
            form_class.base_fields['official_name'].disabled = True
            form_class.base_fields['official_name'].required = False

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
        for role in ActionContactPerson.Role:
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
        FieldPanel('identifier'),
        FieldPanel('official_name'),
        FieldPanel('name'),
        FieldPanel('primary_org', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        FieldPanel('lead_paragraph'),
        FieldPanel('description'),
    ]
    basic_related_panels = [
        FieldPanel('image'),
        CondensedInlinePanel(
            'links',
            panels=[
                FieldPanel('url'),
                FieldPanel('title')
            ],
            heading=_('External links'),
        ),
    ]
    basic_related_panels_general_admin = [
        FieldPanel(
            'related_actions',
            widget=autocomplete.ModelSelect2Multiple(
                url='action-autocomplete',
                forward=(
                    dal_forward.Const(True, 'related_plans'),
                )
            )
        ),
        FieldPanel('merged_with', widget=ActionChooser),
        FieldPanel('visibility'),
    ]

    progress_panels = [
        PlanFilteredFieldPanel('implementation_phase'),
        PlanFilteredFieldPanel('status'),
        FieldPanel('manual_status'),
        FieldPanel('manual_status_reason'),
        FieldPanel('schedule_continuous'),
        FieldPanel('start_date'),
        FieldPanel('end_date'),
    ]
    reporting_panels = [
        FieldPanel('internal_notes', widget=AdminAutoHeightTextInput(attrs=dict(rows=5))),
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
                cat_panels.append(FieldPanel(key, heading=field.label))
            if cat_panels:
                panels.append(MultiFieldPanel(cat_panels, heading=_('Categories')))

        for panel in self.basic_related_panels:
            panels.append(panel)

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
        all_tabs.append(ObjectList(contact_persons_panels, heading=_('Contact persons')))

        if is_general_admin:
            all_tabs.append(
                ObjectList([
                    InlinePanel(
                        'responsible_parties',
                        heading=_('Responsible parties'),
                        panels=[
                            FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
                            FieldPanel('role'),
                            FieldPanel('specifier'),
                        ]
                    )
                ], heading=_('Responsible parties'))
            )
        else:
            all_tabs.append(
                ObjectList([
                    ReadOnlyInlinePanel(
                        heading=_('Responsible parties'),
                        relation_name='responsible_parties')
                ], heading=_('Responsible parties')),
            )

        all_tabs += [
            ObjectList([
                CondensedInlinePanel(
                    'tasks',
                    panels=task_panels,
                )
            ], heading=plan.general_content.get_action_task_term_display_plural()),
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
        reporting_panels += list(self.reporting_panels)

        if is_general_admin:
            reporting_panels.append(
                FieldPanel('internal_admin_notes', widget=AdminAutoHeightTextInput(attrs=dict(rows=5)))
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
            return [ContactPersonsPanel(editable_roles=editable_contact_person_roles)]
        return [ContactPersonsPanel()]
