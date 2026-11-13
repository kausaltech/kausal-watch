from __future__ import annotations

import json
import logging
import typing
from functools import cached_property
from importlib.util import find_spec
from typing import Any, ClassVar, Unpack, cast

from django.conf import settings
from django.contrib import messages as django_messages
from django.contrib.admin.utils import quote
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import ValidationError
from django.db.models import Q, prefetch_related_objects
from django.forms import BaseModelForm, BaseModelFormSet, ModelChoiceField
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.forms import childformset_factory
from wagtail import hooks
from wagtail.admin import messages
from wagtail.admin.forms.models import WagtailAdminModelForm, formfield_for_dbfield
from wagtail.admin.panels import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
)
from wagtail.admin.panels.base import Panel, get_form_for_model
from wagtail.admin.ui.components import MediaContainer
from wagtail.admin.ui.tables import Column
from wagtail.admin.utils import get_latest_str
from wagtail.admin.widgets import AdminAutoHeightTextInput
from wagtail.admin.widgets.button import ListingButton
from wagtail.log_actions import registry as log_registry
from wagtail.snippets.models import register_snippet
from wagtail.snippets.side_panels import SnippetStatusSidePanel
from wagtail.snippets.views.snippets import UnpublishView, WorkflowHistoryDetailView, WorkflowHistoryView

from dal import autocomplete, forward as dal_forward

from kausal_common.people.chooser import PersonChooser
from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request, get_admin_cache
from aplans.utils import naturaltime
from aplans.wagtail_utils import _get_category_fields

from actions.chooser import ActionChooser
from actions.models.action import _renormalize_pks_for_unique_constraint
from actions.models.plan import Plan
from admin_site.field_customization import collect_customizable_field_names, register_customizable_fields
from admin_site.models import BuiltInFieldCustomization
from admin_site.utils import FieldLabelRenderer, admin_req
from admin_site.viewsets import (
    InstancePermissionCheckedMixin,
    WatchCreateView,
    WatchEditView,
    WatchIndexView,
    WatchRevisionsCompareView,
    WatchViewSet,
)
from admin_site.wagtail import (
    AdminOnlyPanel,
    AplansTabbedInterface,
    BuiltInFieldCustomizationAwareEditHandlerMixin,
    CondensedInlinePanel,
    CustomizableBuiltInFieldPanel,
    CustomizableBuiltInPlanFilteredFieldPanel,
    PlanFilteredFieldPanel,
    gate_panel_visibility,
    get_dataset_listing_buttons,
    get_translation_tabs,
    insert_model_translation_panels,
)
from orgs.models import Organization
from people.chooser import TaskPersonChooser
from people.models import Person
from reports.views import MarkActionAsCompleteView

from .admin_utils import change_log_message_url_or_none
from .bulk_approve import BulkApproveView
from .category_admin import InitialPlanFormMixin, PanelFormMixin
from .models.action import (
    Action,
    ActionContactPerson,
    ActionResponsibleParty,
    ActionTask,
)
from .validation import TASK_DUE_DATE_REQUIRED_MESSAGE, get_action_dates_error, get_task_completion_date_error

if typing.TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from django.db.models import Model
    from django.http import HttpRequest
    from django_stubs_ext import StrOrPromise
    from wagtail.admin.panels.group import PanelGroupInitArgs
    from wagtail.snippets.action_menu import ActionMenuItem

    from actions.attributes import DraftAttributes
    from actions.permission_policy import ActionPermissionPolicy
    from users.models import User

    from .models.action import ModelWithRole


logger = logging.getLogger(__name__)


class ReadOnlyInlinePanel(Panel):
    """Variant of InlinePanel where no form inputs are output."""

    relation_name: str

    def __init__(self, relation_name: str, *args, **kwargs):
        self.relation_name = relation_name
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        """Return a dictionary of keyword arguments that can be used to create a clone of this panel definition."""
        result = super().clone_kwargs()
        result['relation_name'] = self.relation_name
        return result

    class BoundPanel(Panel.BoundPanel[Any, Any, Any]):
        panel: ReadOnlyInlinePanel

        template_name = 'aplans/panels/read_only_inline_panel.html'

        def get_context_data(self, parent_context=None):
            context = super().get_context_data(parent_context)
            relation_name = self.panel.relation_name
            context['items'] = [
                {
                    'label': el.get_label() if hasattr(el, 'get_label') else '',
                    'value': el.get_value() if hasattr(el, 'get_value') else str(el),
                }
                for el in getattr(self.instance, relation_name).all()
            ]
            return context


MODELS_WITH_ROLES: list[tuple[type[ModelWithRole[Any]], str, type[Model], str]] = [
    (ActionContactPerson, 'contact_persons', Person, 'person'),
    (ActionResponsibleParty, 'responsible_parties', Organization, 'organization'),
]


class CustomizedFieldAccessMixin[M: Model](BaseModelForm[M]):
    """Helpers for a model form whose fields field customization may leave out or disable."""

    def _is_field_editable(self, field_name: str) -> bool:
        """Return whether the form lets the user edit the field, i.e., field customization neither hid nor disabled it."""
        field = self.fields.get(field_name)
        return field is not None and not field.disabled

    def _get_value(self, field_name: str) -> Any:
        """Return the field's submitted value, or the stored one if the form doesn't have the field."""
        if field_name in self.fields:
            return self.cleaned_data.get(field_name)
        return getattr(self.instance, field_name)


class ActionAdminForm(CustomizedFieldAccessMixin[Action], WagtailAdminModelForm[Action]):
    def __init__(self, *args, **kwargs):
        self.initial_plan_id = kwargs.pop('initial_plan_id', None)
        kwargs.pop('plan', None)
        super().__init__(*args, **kwargs)
        # There is a corresponding formset for a role if and only if we can edit contact persons of that role.
        for cls, relation_name, __, ___ in MODELS_WITH_ROLES:
            for role in cls.get_roles():
                # For some models, the role can be blank
                # OMG, we're really hacking this so that a formset is called, e.g., `responsible_parties_None`...
                formset = self.formsets.get(f'{relation_name}_{role}')
                if formset and formset.queryset is not None:
                    formset.queryset = formset.queryset.filter(role=role)

    def clean_identifier(self):
        # Since we hide the plan in the form, `validate_unique()` will be called with `exclude` containing `plan`, in
        # which case the unique_together constraints of Action will not be checked. We do it manually here.
        identifier = self.cleaned_data['identifier']
        plan = self.instance.plan
        if Action.objects.filter(plan=plan, identifier=identifier).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_('There is already an action with this identifier.'))
        return identifier

    def _get_formsets_for_relation(self, _cls: type[ModelWithRole[Any]], relation_name: str) -> list[BaseModelFormSet[Any, Any]]:
        """Return the formsets editing the given relation: either one for all roles or one per editable role."""
        names = [relation_name, *(f'{relation_name}_{role}' for role in _cls.get_roles())]
        return [self.formsets[name] for name in names if name in self.formsets]

    def _validate_unique_relations_with_roles(
        self,
        _cls: type[ModelWithRole[Any]],
        relation_name: str,
        wrapped_object_attr: str,
    ) -> None:
        """
        Check that no person (or organization) would end up in the relation twice after saving.

        The result consists of the rows in the submitted forms plus the rows of the relation that no submitted form
        covers. The latter are the rows of roles we cannot edit, but also rows that were added after the form was
        loaded, e.g., by an earlier submission of the same form. If such a stale form adds one of those again, saving
        would violate the unique constraint, so we reject it here.
        """
        formsets = self._get_formsets_for_relation(_cls, relation_name)
        if not all(formset.is_valid() for formset in formsets):
            # The formsets show their own errors, and invalid forms have no `cleaned_data` to check.
            return

        seen_wrapped_ids: set[int] = set()
        covered_pks: set[int] = set()
        for formset in formsets:
            deleted_forms = formset.deleted_forms
            for form in formset.forms:
                if form.instance.pk is not None:
                    covered_pks.add(form.instance.pk)
                obj = form.cleaned_data.get(wrapped_object_attr)
                if obj is None or form in deleted_forms:
                    continue
                if obj.pk in seen_wrapped_ids:
                    raise ValidationError(_('%s is listed multiple times in the action.') % obj)
                seen_wrapped_ids.add(obj.pk)

        for item in getattr(self.instance, relation_name).all():
            # Rows without a pk only exist in a draft; if no form covers them, saving drops them.
            if item.pk is None or item.pk in covered_pks:
                continue
            if getattr(item, f'{wrapped_object_attr}_id') in seen_wrapped_ids:
                raise ValidationError(
                    _('%s has been added to the action in the meantime. Please reload the page and try again.')
                    % getattr(item, wrapped_object_attr)
                )

    def _validate_dates(self) -> None:
        """
        Check that the end date is not before the start date, but only if this save changes one of them.

        The error goes on the end date unless field customization hides it from the user or makes it
        read-only, as the user could not fix it there.
        """
        date_fields = ('start_date', 'end_date')
        if not any(name in self.changed_data for name in date_fields):
            return
        if any(name in self.fields and name not in self.cleaned_data for name in date_fields):
            # The field has an error of its own already
            return
        error = get_action_dates_error(self._get_value('start_date'), self._get_value('end_date'))
        if error is None:
            return
        field_name = next((name for name in reversed(date_fields) if self._is_field_editable(name)), None)
        self.add_error(field_name, error)

    def _validate_task_completion_dates(self) -> None:
        """
        Check that no task's completion date is in the future, but only for the tasks whose completion date this save changes.

        `ActionTask.clean()` can't do this check as it can't look up the plan's time zone: a new task
        doesn't have its action yet, as `ActionTask.action` is a `ParentalKey`.
        """
        formset = self.formsets.get('tasks')
        if formset is None:
            return
        plan = self.instance.plan
        # Make the task forms clean themselves, if they haven't yet. Invalid ones are checked too, as far as
        # their completion date is valid.
        formset.is_valid()
        for form in formset.forms:
            cleaned_data = getattr(form, 'cleaned_data', None)
            if not cleaned_data or cleaned_data.get('DELETE'):
                continue
            if 'completed_at' not in form.changed_data:
                continue
            error = get_task_completion_date_error(cleaned_data.get('completed_at'), plan)
            if error is not None:
                form.add_error('completed_at', error)

    def clean(self):
        for _cls, relation_name, __, wrapped_object_attr in MODELS_WITH_ROLES:
            self._validate_unique_relations_with_roles(_cls, relation_name, wrapped_object_attr)
            # Persons can only have at most one role as a contact person.
            # Organizations can only have at most one role as a responsible party
        self._validate_dates()
        self._validate_task_completion_dates()

    def save(self, commit=True):  # noqa: C901, PLR0912
        initial_plan_id = self.initial_plan_id
        # Use initial_plan_id to detect mismatch between the active plan and the initial plan on form load.
        if initial_plan_id and str(initial_plan_id) != str(self.instance.plan.id):
            initial_plan = Plan.objects.get(id=initial_plan_id)

            request = ctx_request.get()
            django_messages.add_message(
                request,
                django_messages.WARNING,
                _(
                    'While editing this action you have switched to a different plan. '
                    'This action was still saved with the original plan "%s".'
                )
                % initial_plan.name,
            )
            self.instance.plan = initial_plan

        if hasattr(self.instance, 'updated_at'):
            self.instance.updated_at = timezone.now()

        # Extract role-based formsets BEFORE calling super().save() to prevent double processing
        role_based_formsets_by_relation = {}
        for _cls, relation_name, __, ___ in MODELS_WITH_ROLES:
            formsets = {}
            # There is a corresponding formset for a role if and only if we can edit objects of that role.
            for role in _cls.get_roles():
                formset = cast('dict', self.formsets).pop(f'{relation_name}_{role}', None)
                if formset:
                    formsets[role] = formset
            if formsets:
                role_based_formsets_by_relation[relation_name] = (_cls, formsets)

        obj: Action = super().save(commit)

        # Now handle the role-based formsets with renormalization logic
        for relation_name, (_cls, formsets) in role_based_formsets_by_relation.items():
            manager = getattr(obj, relation_name)
            original_objects = manager.get_object_list().copy()
            self.save_related_objects_with_role(manager, formsets, original_objects, commit)

        # Update categories
        plan = obj.plan
        for field_name, field in _get_category_fields(plan, Action, obj, user=self._user).items():
            field_data = self.cleaned_data.get(field_name)
            if field_data is None:
                continue
            cat_type = field.category_type
            obj.set_categories(cat_type, field_data)

        if commit:
            # The instance was saved already when we called `super().save()`, but things like the categories may have
            # changed afterwards without being committed.
            obj.save()

        user = self._user
        # If we are serializing a draft (which happens when `commit` is false), we should include all attributes, i.e.,
        # also the non-editable ones. If we are saving a model instance, we only save the editable attributes.
        if commit:
            attribute_types = obj.get_editable_attribute_types(user)
        else:
            attribute_types = obj.get_visible_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.on_form_save(obj, self.cleaned_data, commit=commit)
        return obj

    def _renormalize_pks_for_swaps(
        self, db_objects: list[ModelWithRole], saved_objects: list[ModelWithRole], wrapped_attr: str
    ) -> None:
        """
        Renormalize PKs in formset objects to avoid swap conflicts.

        When organizations/persons are swapped between roles, reassign PKs to ensure
        each wrapped object (org/person) is assigned to the DB record that currently
        has that wrapped object. This prevents IntegrityError from unique_together.

        Args:
            db_objects: List of original objects from the database
            saved_objects: List of instances from formsets (may have swapped wrapped objects)
            wrapped_attr: Name of the FK field ('organization' or 'person')

        """

        # Define accessors for model instances
        def get_pk_model(item) -> int | None:
            return item.pk

        def set_pk_model(item, pk: int | None) -> None:
            item.pk = pk
            item.id = pk

        def get_wrapped_id_model(item) -> int | None:
            return getattr(item, f'{wrapped_attr}_id')

        # Call generic renormalization (both db and target items are model instances)
        _renormalize_pks_for_unique_constraint(
            db_items=db_objects,
            target_items=saved_objects,
            get_pk_db=get_pk_model,
            get_wrapped_id_db=get_wrapped_id_model,
            get_pk_target=get_pk_model,
            set_pk_target=set_pk_model,
            get_wrapped_id_target=get_wrapped_id_model,
        )

    def save_related_objects_with_role(self, manager, formsets, original_objects, commit=True):
        """
        Save the related objects from the given role-specific formsets.

        For contact persons: If the plan does not distinguish contact persons by role, then there are no role-specific
        formsets and the contact persons (in the formset `contact_persons`) are saved in `super().save()`.
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
            # Check if we need special handling for organization/person swaps
            # wrapped_object_attr is the 4th element in MODELS_WITH_ROLES tuple
            wrapped_attr = None
            for _cls, _relation_name, _wrapped_model, _wrapped_attr in MODELS_WITH_ROLES:
                if manager.model == _cls:
                    wrapped_attr = _wrapped_attr
                    break

            # Renormalize PKs to avoid swap conflicts
            if wrapped_attr:
                self._renormalize_pks_for_swaps(original_objects, saved_objects, wrapped_attr)

            # Now commit with renormalized PKs
            manager.commit()


class ModelWithRoleInlinePanel(InlinePanel):
    @staticmethod
    def create_for_model_class(_cls: type[ModelWithRole], *args, **kwargs) -> InlinePanel | None:
        if _cls == ActionResponsibleParty:
            return ResponsiblePartiesInlinePanel(*args, **kwargs)
        if _cls == ActionContactPerson:
            return ContactPersonsInlinePanel(*args, **kwargs)
        return None

    def __init__(self, filter_by_role: bool, role: ModelWithRole.Role | None = None, *args, **kwargs):
        """
        If `filter_by_role` is false, we show all instances in this panel, otherwise only the ones with the given role.

        (`None` is a possible role for ActionResponsibleParty.).

        For the latter to work, make sure that your form contains formsets `contact_persons_<role>` (or equivalent for
        other models) whose querysets are filtered accordingly.
        """
        self.filter_by_role = filter_by_role
        self.role = role
        kwargs.setdefault('panels', self.get_panels())
        if filter_by_role:
            kwargs['relation_name'] = self.get_relation_name(role=role)
            heading: StrOrPromise
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
        assert (
            self.filter_by_role and self.relation_name == self.get_relation_name(self.role)
        ) or self.relation_name == self.get_relation_name()
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
        *args,
        **kwargs,
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
        template_name = 'aplans/panels/read_only_inline_panel.html'

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
                    'value': el.get_value() if hasattr(el, 'get_value') else str(el),
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
            FieldPanel('primary_contact'),
        ]


class RelatedModelWithRolePanel(MultiFieldPanel):
    def __init__(
        self,
        action: Action,
        relation_name: str,
        _cls: type[ModelWithRole],
        editable_roles: Iterable[ModelWithRole.Role | None] | None = None,
        **kwargs: Unpack[PanelGroupInitArgs],
    ):
        """
        Display inline panels for contact persons, optionally separated by roles.

        If `editable_roles` is None, a single inline panel will be shown for all contact persons without distuinguishing
        them by roles.

        Otherwise an inline panel will be included for each role, no matter if it is included in `editable_roles`. The
        type of the panel will differ, however, depending on whether contact persons with that role can be edited.
        """
        self.action = action
        self.relation_name = relation_name
        self._cls = _cls
        self.editable_roles = editable_roles
        children: list[Panel] = []
        assert _cls  # TODO: Didn't really check when or if it can actually be None
        if editable_roles is None:
            panel = ModelWithRoleInlinePanel.create_for_model_class(_cls, filter_by_role=False)
            assert panel is not None
            children.append(panel)
        else:
            for role in _cls.get_roles():
                # Only show panel for "unspecified" role if there are instances with an unspecified role
                # https://github.com/kausaltech/kausal-watch/pull/111#issuecomment-1896291423
                if role is None and not getattr(action, relation_name).filter(role__isnull=True).exists():
                    continue
                if role in editable_roles:
                    panel = ModelWithRoleInlinePanel.create_for_model_class(_cls, filter_by_role=True, role=role)
                else:
                    panel = ModelWithRoleReadOnlyInlinePanel(relation_name, filter_by_role=True, role=role)
                assert panel is not None
                children.append(cast('Panel', panel))
        super().__init__(children=children, **kwargs)

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        # children are statically set in __init__
        kwargs.pop('children')
        kwargs['action'] = self.action
        kwargs['relation_name'] = self.relation_name
        kwargs['_cls'] = self._cls
        kwargs['editable_roles'] = self.editable_roles
        return kwargs


class ActionEditHandler(
    BuiltInFieldCustomizationAwareEditHandlerMixin[Action, ActionAdminForm], AplansTabbedInterface[Action, ActionAdminForm]
):
    def __init__(self, *args, draft_attributes: DraftAttributes | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.draft_attributes = draft_attributes

    def clone_kwargs(self):
        result = super().clone_kwargs()
        result['draft_attributes'] = self.draft_attributes
        return result

    def get_form_class(self):  # noqa: C901, PLR0912
        request = ctx_request.get()
        instance = ctx_instance.get_as_type(Action)
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        cat_fields = _get_category_fields(plan, Action, instance, with_initial=True, user=user)

        if instance is not None:
            attribute_types = instance.get_visible_attribute_types(user)
            attribute_fields = {
                field.name: field.django_field
                for attribute_type in attribute_types
                for field in attribute_type.get_form_fields(
                    user,
                    plan,
                    instance,
                    draft_attributes=self.draft_attributes,
                )
            }
        else:
            attribute_fields = {}
        self.base_form_class = type(  # pyright: ignore
            'ActionAdminForm',
            (ActionAdminForm,),
            {**cat_fields, **attribute_fields, '_user': user},
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

        formsets = dict[str, type[BaseModelFormSet[Any, Any]] | BaseModelFormSet[Any, Any]](form_class.formsets)

        # TODO: Move this to BuiltInFieldCustomizationAwareEditHandlerMixin or somewhere else so it can be reused?
        if not user.is_general_admin_for_plan(plan):
            for panel in list(self.children):
                if not isinstance(panel, AdminOnlyPanel):
                    continue
                for child in panel.children:
                    if isinstance(child, FieldPanel):
                        del form_class.base_fields[child.field_name]
                    elif isinstance(child, InlinePanel):
                        del formsets[child.relation_name]
                    else:
                        raise TypeError('Invalid child panel: %s' % child)

        field = form_class.base_fields.get('impact')
        if field is not None:
            field.queryset = field.queryset.filter(plan=plan)

        field = form_class.base_fields.get('status')
        if field is not None:
            field.queryset = field.queryset.filter(plan=plan)

        # Manually add a formset for each contact person role whose contact persons we may edit.
        # There is a corresponding formset in the form options if and only if we can edit contact persons of a
        # certain role.
        for acp_role in ActionContactPerson.get_roles():
            form_options = self.get_form_options()
            formset_name = f'contact_persons_{acp_role}'
            formset_options = form_options['formsets'].get(formset_name)
            if formset_options:
                kwargs = {
                    'extra': 0,
                    'fk_name': 'action',
                    'form': WagtailAdminModelForm,
                    'formfield_callback': formfield_for_dbfield,
                    **form_options['formsets'][formset_name],
                }
                formsets[formset_name] = childformset_factory(Action, ActionContactPerson, **kwargs)

        for arp_role in ActionResponsibleParty.get_roles():
            form_options = self.get_form_options()
            formset_name = f'responsible_parties_{arp_role}'
            formset_options = form_options['formsets'].get(formset_name)
            if formset_options:
                kwargs = {
                    'extra': 0,
                    'fk_name': 'action',
                    'form': WagtailAdminModelForm,
                    'formfield_callback': formfield_for_dbfield,
                    **form_options['formsets'][formset_name],
                }
                formsets[formset_name] = childformset_factory(Action, ActionResponsibleParty, **kwargs)
        form_class.formsets = formsets
        return form_class


class ActionInstanceContextMixin:
    """Make the action available as `ctx_instance`, which the edit handler needs for building the form class."""

    def get_context_instance(self) -> Action:
        raise NotImplementedError

    def dispatch(self, request, *args, **kwargs):
        with ctx_instance.activate(self.get_context_instance()):
            response = super().dispatch(request, *args, **kwargs)  # type: ignore[misc]
            if hasattr(response, 'render'):
                response = response.render()
            return response


def _get_action_viewset() -> ActionViewSet:
    return cast('ActionViewSet', Action.snippet_viewset)  # type: ignore[attr-defined]


class ActionCreateView(
    InitialPlanFormMixin, ActionInstanceContextMixin, PanelFormMixin, WatchCreateView[Action, ActionAdminForm]
):
    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        # A new action is saved as it is; only later edits are held back as drafts
        self.draftstate_enabled = False
        self.autosave_enabled = False
        self.saving_as_draft = False

    @cached_property
    def new_action(self) -> Action:
        instance = Action()
        self.initialize_instance(self.request, instance)
        return instance

    def get_context_instance(self) -> Action:
        return self.new_action

    def get_initial_form_instance(self):
        return self.new_action

    def get_panel(self):
        with ctx_instance.activate(self.new_action):
            return _get_action_viewset().build_edit_handler().bind_to_model(Action)

    def get_side_panels(self):
        return MediaContainer()

    def initialize_instance(self, request, instance: Action) -> None:
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        assert instance.pk is None
        assert not hasattr(instance, 'plan')
        instance.plan = plan
        if not plan.features.has_action_identifiers:
            assert not instance.identifier
            instance.generate_identifier()
        if plan.features.has_action_primary_orgs:
            assert instance.primary_org is None
            person = user.get_corresponding_person()
            if person is not None:
                available_orgs = Organization.objects.get_queryset().available_for_plan(plan)
                default_org = available_orgs.filter(id=person.organization_id).first()
                instance.primary_org = default_org

    def get_success_url(self):
        assert self.object is not None
        if self.object.plan.features.moderation_workflow is None:
            url = change_log_message_url_or_none(self.object, moderation_enabled=False)
            return url or super().get_success_url()
        return super().get_success_url()


class ActionEditView(
    InitialPlanFormMixin,
    ActionInstanceContextMixin,
    PanelFormMixin,
    WatchEditView[Action, ActionAdminForm],
    # Last, so that the workflow rules of Wagtail's edit view come before the check of the action itself
    InstancePermissionCheckedMixin,
):
    object: Action
    live_object: Action
    workflow_action: str

    def setup(self, request, *args, **kwargs):
        super().setup(request, *args, **kwargs)
        self.autosave_enabled = False
        self.saving_as_draft = False

    def get_object(self, queryset=None):
        # Plans without a moderation workflow save actions directly, without drafts or locks
        self.draftstate_enabled = False
        live_object = super().get_object(queryset)
        if not live_object.plan.features.enable_moderation_workflow:
            self.locking_enabled = False
            return live_object
        self.draftstate_enabled = True
        return live_object.get_latest_revision_as_object()

    def get_context_instance(self) -> Action:
        return self.object

    def get_panel(self):
        with ctx_instance.activate(self.object):
            return _get_action_viewset().build_edit_handler(instance_being_edited=self.object).bind_to_model(Action)

    def get_last_updated_info(self):
        live_object = getattr(self, 'live_object', None)
        if self.draftstate_enabled and live_object is not None and live_object.live and live_object.live_revision is None:
            # The newest revision would be a draft, not the live version
            return log_registry.get_logs_for_instance(live_object).filter(action='wagtail.publish').first()
        return super().get_last_updated_info()

    def get_lock_context(self):
        context = super().get_lock_context()
        if context:
            # Locking by hand is not offered for actions
            context['user_can_lock'] = False
            context['user_can_unlock'] = False
        return context

    def get_side_panels(self):
        side_panels = super().get_side_panels()
        for side_panel in side_panels:
            if isinstance(side_panel, SnippetStatusSidePanel):
                side_panel.locking_enabled = self.locking_enabled
                # The reference index does not cover references between actions
                side_panel.usage_url = None
        return side_panels

    def get_available_actions(self):
        actions = super().get_available_actions()
        if 'publish' in actions and not self.user_has_permission('publish'):
            actions.remove('publish')
        return actions

    def submit_action(self):
        try:
            super().submit_action()
        except ValidationError as e:
            messages.validation_error(self.request, ' '.join(e.messages), self.form)
            self.run_after_hook()
            return redirect(self.get_edit_url())
        url = change_log_message_url_or_none(self.object, moderation_enabled=True)
        if url is None:
            return None
        self.run_after_hook()
        return redirect(url)

    def get_success_message(self, instance=None):
        if (
            self.action == 'workflow-action'
            and self.workflow_action == 'approve'
            and self.workflow_state
            and self.workflow_state.is_at_final_task
            and not getattr(settings, 'WAGTAIL_WORKFLOW_REQUIRE_REAPPROVAL_ON_EDIT', False)
        ):
            return _("%(model_name)s '%(object)s' approved and published.") % {
                'model_name': capfirst(Action._meta.verbose_name),
                'object': get_latest_str(instance or self.object),
            }
        return super().get_success_message(instance)

    def get_success_url(self):
        if self.object.plan.features.moderation_workflow is None:
            url = change_log_message_url_or_none(self.object, moderation_enabled=False)
            return url or super().get_success_url()
        return super().get_success_url()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if self.draftstate_enabled:
            menu = context['action_menu']
            menu.menu_items = [item for item in menu.menu_items if item.name != self.ContinueEditingActionMenuItem.name]
        # Display warnings for any attributes that were lost during draft deserialization
        self._display_draft_attribute_warnings()
        return context

    def _display_draft_attribute_warnings(self) -> None:
        """Display warning messages for any attributes lost during draft deserialization."""
        obj = self.object
        if obj is None:
            return
        if not hasattr(obj, 'draft_attributes') or obj.draft_attributes is None:
            return
        draft_attributes = obj.draft_attributes
        if not draft_attributes.deserialization_warnings:
            return
        for warning in draft_attributes.deserialization_warnings:
            if warning.attribute_type_name:
                msg = _('Field "%(attribute_type)s": %(message)s') % {
                    'attribute_type': warning.attribute_type_name,
                    'message': warning.message,
                }
            else:
                msg = warning.message
            django_messages.warning(self.request, msg)


# Task relations that are edited in an inline panel of their own inside the tasks tab.
TASK_ASSIGNMENT_RELATIONS = ('responsible_parties', 'contact_persons')


class PlanScopedAssignmentForm(WagtailAdminModelForm):
    """
    Child form for a task assignment whose assignee must belong to the plan.

    The chooser and the autocomplete only filter what is *offered*; the generated `ModelChoiceField`
    still accepts every Person or Organization in the database, so an editor could assign another
    tenant's person by posting its id and have it published through the task API. Narrowing the
    queryset makes the field reject those ids during validation.
    """

    plan: ClassVar[Plan | None] = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        plan = self.plan
        if plan is None:
            return
        person_field = self.fields.get('person')
        if isinstance(person_field, ModelChoiceField):
            # Same candidates as `TaskPersonChooser`, including the plan's contact persons from
            # organizations that are not related to it.
            person_field.queryset = Person.objects.available_for_plan(plan, include_contact_persons=True)
        organization_field = self.fields.get('organization')
        if isinstance(organization_field, ModelChoiceField):
            # An organization can leave the plan's hierarchy while a task is still assigned to it, so the
            # value this row already holds stays valid; otherwise the action could not be saved again
            # until the assignment was removed. Only that one value, though: accepting every
            # organization historically assigned in the plan would let a departed one be posted onto any
            # other task, which is the cross-plan assignment this queryset exists to prevent.
            allowed = Q(pk__in=Organization.objects.available_for_plan(plan).values('pk'))
            stored_organization_id = getattr(self.instance, 'organization_id', None)
            if stored_organization_id is not None:
                allowed |= Q(pk=stored_organization_id)
            organization_field.queryset = Organization.objects.filter(allowed)


class ActionTaskForm(CustomizedFieldAccessMixin[ActionTask], WagtailAdminModelForm[ActionTask]):
    """
    Child form for an action task, which requires a due date unless the task is continuous.

    The `ActionTask` check constraint can't do this for the form: Django skips a constraint when the form
    leaves out one of its fields, which field customization may do to either of them. The error goes on
    the field the user can change: the due date if possible, otherwise the continuity flag.
    """

    def clean(self):
        cleaned_data = super().clean()
        if 'due_at' in self.errors:
            # The field has an error of its own already
            return cleaned_data
        if self._get_value('is_continuous') or self._get_value('due_at') is not None:
            return cleaned_data
        field_name = next((name for name in ('due_at', 'is_continuous') if self._is_field_editable(name)), None)
        self.add_error(field_name, TASK_DUE_DATE_REQUIRED_MESSAGE)
        return cleaned_data


class ActionTaskInlinePanel(CondensedInlinePanel[Action, ActionTask]):
    """Inline panel for an action's tasks, with `ActionTaskForm` as the child form."""

    def get_form_options(self):
        options = super().get_form_options()
        # Like `InlinePanel.get_form_options()`, which sets a child form of its own if there are fields to defer
        # the `required` check on, and those must not get lost.
        meta_options = {}
        defer_required_on_fields = self.child_edit_handler.get_form_options().get('defer_required_on_fields')
        if defer_required_on_fields:
            meta_options['defer_required_on_fields'] = defer_required_on_fields
        options['formsets'][self.relation_name]['form'] = get_form_for_model(
            ActionTask, form_class=ActionTaskForm, **meta_options
        )
        return options


class TaskAssignmentInlinePanel(InlinePanel):
    """Inline panel for a task assignment relation, with its child form scoped to `plan`."""

    def __init__(self, relation_name: str, *args, plan: Plan | None = None, **kwargs):
        self.plan = plan
        super().__init__(relation_name, *args, **kwargs)

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        kwargs['plan'] = self.plan
        return kwargs

    def bound_to_plan(self, plan: Plan) -> TaskAssignmentInlinePanel:
        """Return a copy of this panel whose child form accepts only `plan`'s assignees."""
        kwargs = self.clone_kwargs()
        kwargs['plan'] = plan
        return type(self)(**kwargs)

    def get_form_options(self):
        options = super().get_form_options()
        if self.plan is not None:
            options['formsets'][self.relation_name]['form'] = type(
                'PlanScopedAssignmentForm',
                (PlanScopedAssignmentForm,),
                {'plan': self.plan},
            )
        return options


class ActionIndexView(WatchIndexView[Action]):
    def get_base_queryset(self):
        return super().get_base_queryset().order_by('order')

    @cached_property
    def columns(self):  # type: ignore[override]
        plan = admin_req(self.request).user.get_active_admin_plan()
        columns: list[Column] = [self._get_title_column('name')]
        if plan.features.has_action_identifiers:
            columns.insert(0, Column('identifier', label=_('Identifier'), sort_key='identifier'))
        if plan.features.has_action_primary_orgs:
            columns.insert(0, Column('primary_org', label=_('Primary organization')))
        category_type = plan.category_types.filter(identifier='action').first()
        if category_type is not None:
            columns.append(
                Column(
                    'action_category',
                    label=category_type.name,
                    accessor=lambda action: '; '.join(
                        str(category) for category in action.categories.all() if category.type_id == category_type.id
                    ),
                )
            )
        columns.append(Column('updated_at_delta', label=_('Last updated'), accessor=_get_updated_at_delta))
        return columns

    def get_edit_url(self, instance: Action):
        assert self.permission_policy is not None
        if not self.permission_policy.user_has_permission_for_instance(self.request.user, 'change', instance):
            return None
        return super().get_edit_url(instance)

    def get_list_more_buttons(self, instance: Action):
        user = admin_req(self.request).user
        return _get_action_viewset().get_index_view_buttons(user, instance, user.get_active_admin_plan())


def _get_updated_at_delta(action: Action) -> str | None:
    if not action.updated_at:
        return None
    return naturaltime(action.plan.now_in_local_timezone() - action.updated_at)


class ActionUnpublishView(InstancePermissionCheckedMixin, UnpublishView):
    pass


class ActionWorkflowHistoryView(InstancePermissionCheckedMixin, WorkflowHistoryView):
    pass


class ActionWorkflowHistoryDetailView(InstancePermissionCheckedMixin, WorkflowHistoryDetailView):
    pass


class ActionRevisionsCompareView(WatchRevisionsCompareView[Action]):
    def get_edit_handler(self):
        with ctx_instance.activate(self.object):
            return _get_action_viewset().build_edit_handler(instance_being_edited=self.object).bind_to_model(Action)

    def dispatch(self, request, *args, **kwargs):
        with ctx_instance.activate(self.object):
            response = super().dispatch(request, *args, **kwargs)
            if hasattr(response, 'render'):
                response = response.render()
            return response


# Views of Wagtail's snippet viewset that are not offered for actions
DISABLED_URL_NAMES = frozenset({
    'lock',
    'unlock',
    'revisions_revert',
    'revisions_unschedule',
    'workflow_action',
})


class ActionViewSet(WatchViewSet[Action, ActionAdminForm]):
    model = Action
    url_prefix = 'actions/action'
    icon = 'kausal-action'
    menu_order = 10
    menu_label = pgettext_lazy('Action model', 'Actions')
    add_to_admin_menu = True
    search_fields = ['identifier', 'name']
    # Search the database like the ModelAdmin did, as the search index cannot filter by plan
    search_backend_name = None
    bulk_delete_enabled = False
    index_view_class = ActionIndexView
    add_view_class = ActionCreateView
    edit_view_class = ActionEditView
    unpublish_view_class = ActionUnpublishView
    revisions_compare_view_class = ActionRevisionsCompareView
    workflow_history_view_class = ActionWorkflowHistoryView
    workflow_history_detail_view_class = ActionWorkflowHistoryDetailView
    bulk_approve_view_class = BulkApproveView

    # The form is built per request in `build_edit_handler()`; this one only serves the registration
    edit_handler = ObjectList([FieldPanel('name')], base_form_class=ActionAdminForm)

    basic_panels: Sequence[Panel[Action]] = (
        CustomizableBuiltInFieldPanel[Action]('identifier'),
        CustomizableBuiltInFieldPanel[Action]('official_name'),
        CustomizableBuiltInFieldPanel[Action]('name'),
        CustomizableBuiltInFieldPanel[Action]('primary_org', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        CustomizableBuiltInFieldPanel[Action]('lead_paragraph'),
        CustomizableBuiltInFieldPanel[Action]('description'),
    )
    basic_related_panels: Sequence[Panel[Action]] = (CustomizableBuiltInFieldPanel('image'),)
    basic_related_panels_general_admin: list[Panel[Any]] = [
        CustomizableBuiltInFieldPanel(
            'related_actions',
            widget=autocomplete.ModelSelect2Multiple(
                url='action-autocomplete',
                forward=(dal_forward.Const(val=True, dst='related_plans'),),
            ),
        ),
        CustomizableBuiltInFieldPanel('merged_with', widget=ActionChooser),
        CustomizableBuiltInFieldPanel('visibility'),
    ]

    progress_panels: list[Panel[Any]] = [
        CustomizableBuiltInPlanFilteredFieldPanel('implementation_phase'),
        CustomizableBuiltInPlanFilteredFieldPanel('status'),
        CustomizableBuiltInFieldPanel('manual_status'),
        CustomizableBuiltInFieldPanel('manual_status_reason'),
        CustomizableBuiltInFieldPanel('schedule_continuous'),
        CustomizableBuiltInFieldPanel('start_date'),
        CustomizableBuiltInFieldPanel('end_date'),
        CustomizableBuiltInFieldPanel('date_format'),
    ]

    task_panels: list[Panel[Any]] = [
        CustomizableBuiltInFieldPanel('name'),
        CustomizableBuiltInFieldPanel('is_continuous'),
        CustomizableBuiltInFieldPanel('due_at'),
        CustomizableBuiltInFieldPanel('date_format'),
        CustomizableBuiltInFieldPanel('state'),
        CustomizableBuiltInFieldPanel('completed_at'),
        CustomizableBuiltInFieldPanel('details'),
        TaskAssignmentInlinePanel(
            'responsible_parties',
            panels=[FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete'))],
            heading=_('Responsible parties'),
        ),
        TaskAssignmentInlinePanel(
            'contact_persons',
            # `TaskPersonChooser`, not `PersonChooser`: task assignment must also reach the plan's contact
            # persons from unrelated organizations (see `src/people/chooser.py`).
            panels=[FieldPanel('person', widget=TaskPersonChooser)],
            heading=_('Contact persons'),
        ),
    ]

    task_header_from_js = """
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
    """

    def get_task_header_formatter(self):
        states = {key: str(label) for key, label in list(ActionTask.STATES)}
        out = self.task_header_from_js % dict(state_map=json.dumps(states))
        return out

    def build_edit_handler(self, instance_being_edited: Action | None = None):  # noqa: C901, PLR0912, PLR0915
        request = ctx_request.get()
        instance = ctx_instance.get_as_type(Action)
        # TODO: find out how to include the relevant draftable mixin state
        # to the context instance so no separate instance_being_edited would
        # be needed.

        assert isinstance(instance, Action)
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        assert plan is not None

        render_field_label = FieldLabelRenderer(plan)

        draft_attributes = instance_being_edited.draft_attributes if instance_being_edited else None
        attribute_panels = instance.get_attribute_panels(user, draft_attributes)
        main_attribute_panels, reporting_attribute_panels, i18n_attribute_panels = attribute_panels

        all_tabs: list[Panel[Any]] = []

        is_general_admin = user.is_general_admin_for_plan(plan)
        panels: list[Panel[Action]] = list(self.basic_panels)
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

        cat_fields = _get_category_fields(instance.plan, Action, instance, with_initial=True, user=user)
        cat_panels = []
        for key, field in cat_fields.items():
            cat_panels.append(FieldPanel[Action](key, heading=render_field_label(field.label, public=False)))
        if cat_panels:
            panels.append(MultiFieldPanel(cat_panels, heading=_('Categories')))

        for panel in self.basic_related_panels:
            panels.append(panel)

        panels.append(
            CondensedInlinePanel(
                'links',
                panels=[
                    FieldPanel('url'),
                    FieldPanel('title'),
                ],
                heading=render_field_label(_('External links'), public=True),
            ),
        )

        if is_general_admin:
            panels += self.basic_related_panels_general_admin

            if plan.superseded_by:
                panels.append(
                    FieldPanel(
                        'superseded_by',
                        widget=autocomplete.ModelSelect2(
                            url='action-autocomplete',
                            forward=(dal_forward.Const(plan.superseded_by.id, 'plan'),),
                        ),
                    )
                )

            if plan.copy_of:
                panels.append(
                    FieldPanel(
                        'copy_of',
                        widget=autocomplete.ModelSelect2(
                            url='action-autocomplete',
                            forward=(dal_forward.Const(plan.copy_of.id, 'plan'),),
                        ),
                    )
                )

        all_tabs.append(ObjectList(panels, heading=_('Basic information')))

        progress_panels = list(self.progress_panels)

        # If all of the action statuses are updated manually, remove the
        # manual status toggle.
        if plan.statuses_updated_manually:
            for panel in progress_panels:
                if isinstance(panel, FieldPanel) and panel.field_name == 'manual_status':
                    progress_panels.remove(panel)
                    break

        all_tabs.append(ObjectList(progress_panels, heading=_('Progress')))

        contact_persons_panels = self.get_contact_persons_panels(request, instance)
        all_tabs.append(
            ObjectList(
                contact_persons_panels,
                help_text=render_field_label('', public=plan.features.public_contact_persons),
                heading=_('Contact persons'),
            )
        )

        responsible_parties_panels = self.get_responsible_parties_panels(request, instance)
        all_tabs.append(
            ObjectList(
                responsible_parties_panels, help_text=render_field_label('', public=True), heading=_('Responsible parties')
            )
        )

        # Leaving out the tab also leaves the tasks formset out of the form, so tasks of an action whose tasks are not
        # visible for the user can't be changed either. Note that `label_override` and `help_text_override` of a
        # customization for `tasks` have no effect since the tab heading comes from the plan's general content.
        tasks_visible, _unused = BuiltInFieldCustomization.get_field_access(user, plan, Action, 'tasks', instance)
        if tasks_visible:
            task_panels = list(
                insert_model_translation_panels(ActionTask, self.get_task_panels(user, plan, instance), request, plan)
            )
            all_tabs += [
                ObjectList(
                    [
                        ActionTaskInlinePanel(
                            'tasks',
                            panels=task_panels,
                        ),
                    ],
                    heading=plan.general_content.get_action_task_term_display_plural(),
                    help_text=render_field_label('', public=True),
                ),
            ]

        reporting_panels: list[Panel] = [cast('Panel', panel) for panel in reporting_attribute_panels]
        help_panels_for_field: dict[int, list[Panel]] = {}
        for snapshot in instance.get_snapshots():
            if not snapshot.report.show_in_reporting_tab:
                continue
            for field in snapshot.report.type.fields:
                if not hasattr(field.block, 'get_help_panel'):
                    continue
                help_panel = field.block.get_help_panel(field.value, snapshot)
                if help_panel:
                    help_panels_for_field.setdefault(field.id, []).append(help_panel)
        for help_panels in help_panels_for_field.values():
            reporting_panels += help_panels
        reporting_panels.append(
            FieldPanel(
                'internal_notes',
                heading=render_field_label(_('Internal notes'), public=False),
                widget=AdminAutoHeightTextInput(attrs=dict(rows=5)),
            ),
        )

        if is_general_admin:
            reporting_panels.append(
                FieldPanel(
                    'internal_admin_notes',
                    heading=render_field_label(_('Internal notes for plan administrators'), public=False),
                    widget=AdminAutoHeightTextInput(attrs=dict(rows=5)),
                ),
            )
            if plan.action_impacts.exists():
                reporting_panels.append(PlanFilteredFieldPanel('impact'))
            if plan.action_schedules.exists():
                reporting_panels.append(PlanFilteredFieldPanel('schedule'))

        all_tabs.append(ObjectList(reporting_panels, heading=_('Reporting')))

        if is_general_admin and plan.action_dependency_roles.exists():
            dependency_panels: list[Panel[Any]] = [
                CustomizableBuiltInFieldPanel('dependency_role'),
                CondensedInlinePanel(
                    'dependent_relationships',
                    panels=[
                        FieldPanel('dependent', widget=ActionChooser),
                    ],
                    heading=_('Dependent actions'),
                ),
            ]
            all_tabs.append(ObjectList(dependency_panels, heading=_('Dependencies')))

        i18n_tabs = get_translation_tabs(instance, request, extra_panels=i18n_attribute_panels)
        all_tabs += i18n_tabs

        return ActionEditHandler(
            all_tabs,
            draft_attributes=draft_attributes,
        )

    def get_queryset(self, request):
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        qs = Action.objects.get_queryset()
        if not user.is_general_admin_for_plan(plan):
            qs = qs.unmerged()
        qs = qs.filter(plan=plan)
        qs = qs.select_related('plan').prefetch_related('categories')
        return qs

    def get_common_view_kwargs(self, **kwargs):
        # Locking by hand, reverting and scheduling are not offered for actions
        return super().get_common_view_kwargs(**{
            'lock_url_name': None,
            'unlock_url_name': None,
            'revisions_revert_url_name': None,
            'revisions_unschedule_url_name': None,
            **kwargs,
        })

    @property
    def mark_action_as_complete_view(self):
        return MarkActionAsCompleteView.as_view(index_url_name=self.get_url_name('list'), complete=True)

    @property
    def undo_marking_action_as_complete_view(self):
        return MarkActionAsCompleteView.as_view(index_url_name=self.get_url_name('list'), complete=False)

    @property
    def bulk_approve_in_moderation_view(self):
        return self.bulk_approve_view_class.as_view(model=self.model)

    def get_urlpatterns(self):
        urlpatterns = [pattern for pattern in super().get_urlpatterns() if pattern.name not in DISABLED_URL_NAMES]
        return [
            *urlpatterns,
            path(
                'mark_action_as_complete/<str:action_pk>/<str:report_pk>/',
                self.mark_action_as_complete_view,
                name='mark_action_as_complete',
            ),
            path(
                'undo_marking_action_as_complete/<str:action_pk>/<str:report_pk>/',
                self.undo_marking_action_as_complete_view,
                name='undo_marking_action_as_complete',
            ),
            path('bulk_approve_in_moderation/', self.bulk_approve_in_moderation_view, name='bulk_approve_in_moderation'),
        ]

    def _get_report_buttons(self, user: User, instance: Action, plan: Plan) -> list[ListingButton]:
        buttons: list[ListingButton] = []
        # For each report type, one button for the latest report of that type
        for report in get_admin_cache(ctx_request.get_admin_request()).latest_reports:
            if report.is_complete:
                continue
            if report.type.only_plan_admins_can_mark_actions_as_complete and not user.is_general_admin_for_plan(report.type.plan):
                continue
            args = (quote(instance.pk), quote(report.pk))
            if instance.is_complete_for_report(report):
                button = ListingButton(
                    _('Undo marking as complete for report %s') % report.name,
                    url=reverse(self.get_url_name('undo_marking_action_as_complete'), args=args),
                    attrs={'title': _('Undo marking this action as complete for the report %s') % str(report)},
                )
            else:
                button = ListingButton(
                    _('Mark as complete for report %s') % report.name,
                    url=reverse(self.get_url_name('mark_action_as_complete'), args=args),
                    attrs={'title': _('Mark this action as complete for the report %s') % str(report)},
                )
            buttons.append(button)
        return buttons

    def get_index_view_buttons(self, user: User, instance: Action, plan: Plan) -> list[ListingButton]:
        """
        Return the buttons of an action's row in the listing.

        Defined here and not in the index view so that they can also be queried through GraphQL, for
        the listing that the extensions render themselves.
        """
        policy = cast('ActionPermissionPolicy', self.permission_policy)
        can_edit = policy.user_has_permission_in_own_plan(user, 'change', instance)
        buttons: list[ListingButton] = []
        if can_edit:
            buttons.append(
                ListingButton(
                    _('Edit'),
                    url=reverse(self.get_url_name('edit'), args=(quote(instance.pk),)),
                    icon_name='edit',
                    attrs={'aria-label': _("Edit '%(title)s'") % {'title': str(instance)}},
                    priority=10,
                )
            )
        if policy.user_has_permission_in_own_plan(user, 'delete', instance):
            buttons.append(
                ListingButton(
                    _('Delete'),
                    url=reverse(self.get_url_name('delete'), args=(quote(instance.pk),)),
                    icon_name='bin',
                    attrs={'aria-label': _("Delete '%(title)s'") % {'title': str(instance)}},
                    priority=30,
                )
            )
        request = ctx_request.get_admin_request()
        # Built for every row of a listing, all for the same plan instance
        prefetch_related_objects([plan], 'domains')
        view_url = instance.get_view_url(plan=plan, request=request)
        if view_url:
            buttons.append(
                ListingButton(
                    _('View live'),
                    url=view_url,
                    icon_name='view',
                    attrs={'target': '_blank', 'title': _('View %s live') % Action._meta.verbose_name},
                    priority=60,
                )
            )
        buttons.extend(get_dataset_listing_buttons(request, instance))
        if can_edit:
            buttons.extend(self._get_report_buttons(user, instance, plan))
        for button in buttons:
            # The GraphQL type reads these as attributes
            button.title = button.attrs.get('title')  # type: ignore[attr-defined]
            button.target = button.attrs.get('target')  # type: ignore[attr-defined]
        return buttons

    def _get_field_customization_panels(
        self,
        request: HttpRequest,
        instance: Action,
        field_name: str,
        relation_name: str,
        model_cls: type[ModelWithRole[Any]],
        get_editable_roles_method: str,
    ) -> list[Panel]:
        """
        Handle field customization panels for both contact persons and responsible parties.

        This method creates appropriate panels based on user permissions and field customizations.
        """
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()

        is_visible, is_editable = BuiltInFieldCustomization.get_field_access(user, plan, Action, field_name, instance)
        # if instance is editable, it should be visible too
        if is_editable:
            is_visible = True

        if plan.features.has_action_contact_person_roles or is_editable:
            editable_roles = getattr(request.user, get_editable_roles_method)(instance)
        else:
            editable_roles = []

        panel_cls = gate_panel_visibility(RelatedModelWithRolePanel, is_visible=is_visible)
        panel = panel_cls(
            action=instance,
            relation_name=relation_name,
            _cls=model_cls,
            editable_roles=editable_roles,
        )

        return [panel]

    def get_contact_persons_panels(self, request: HttpRequest, instance: Action):
        return self._get_field_customization_panels(
            request=request,
            instance=instance,
            field_name='contact_persons',
            relation_name='contact_persons',
            model_cls=ActionContactPerson,
            get_editable_roles_method='get_editable_contact_person_roles',
        )

    def get_task_panels(self, user: User, plan: Plan, instance: Action | None) -> list[Panel[Any]]:
        """
        Return the task panels, with each assignment panel gated by its own customization.

        `collect_customizable_field_names()` only picks up `CustomizableBuiltInFieldPanel`s, so an
        `InlinePanel` over a relation is not customizable by declaration alone: the relation name has to
        be registered explicitly (see `register_customizable_fields()` below) and gated here.

        `get_field_access()` returns visibility and editability independently, and editability defaults
        to "authenticated", so neither flag may be read on its own:

        - not visible: drop the panel entirely. That also drops its formset, which is what makes the
          relation non-editable — as for the `tasks` tab, a hidden relation must not be editable either,
          no matter what the (defaulted) editability says.
        - visible but not editable: swap in a `ReadOnlyInlinePanel`, which renders the rows without form
          inputs. Merely hiding the panel would keep the formset in the form and leave the rows writable.
        - both: the editable `InlinePanel` as declared.

        The heading tells whether the relation is public, which the customization's visibility decides too,
        and for contact persons also the plan's contact-person setting.
        """
        render_field_label = FieldLabelRenderer(plan)
        customizations = BuiltInFieldCustomization.for_plan(plan)
        panels: list[Panel[Any]] = []
        for panel in self.task_panels:
            relation_name = getattr(panel, 'relation_name', None)
            if relation_name not in TASK_ASSIGNMENT_RELATIONS:
                panels.append(panel)
                continue
            if not plan.features.has_action_task_assignees:
                # The plan does not have the feature at all; the per-plan customization below only
                # decides who may see it in a plan that does.
                continue
            is_visible, is_editable = BuiltInFieldCustomization.get_field_access(user, plan, ActionTask, relation_name, instance)
            if not is_visible:
                continue
            is_public = BuiltInFieldCustomization.is_field_visible_for(
                AnonymousUser(), plan, ActionTask, relation_name, instance, customizations
            )
            if relation_name == 'contact_persons':
                is_public = is_public and plan.features.public_contact_persons
            heading = render_field_label(panel.heading, public=is_public)
            if not is_editable:
                panels.append(ReadOnlyInlinePanel(relation_name, heading=heading))
                continue
            # Bind the plan so the child form rejects assignees from outside it.
            bound_panel = panel.bound_to_plan(plan) if isinstance(panel, TaskAssignmentInlinePanel) else panel.clone()
            bound_panel.heading = heading
            panels.append(bound_panel)
        return panels

    def get_responsible_parties_panels(self, request: HttpRequest, instance: Action):
        return self._get_field_customization_panels(
            request=request,
            instance=instance,
            field_name='responsible_parties',
            relation_name='responsible_parties',
            model_cls=ActionResponsibleParty,
            get_editable_roles_method='get_editable_responsible_party_roles',
        )


# Built-in fields of actions and action tasks that plan admins may customize. The panel-backed names
# are derived from the panel declarations above so they cannot drift apart; the rest have to be
# listed explicitly because their panels are built per request.
register_customizable_fields(
    Action,
    [
        *collect_customizable_field_names([
            *ActionViewSet.basic_panels,
            *ActionViewSet.basic_related_panels,
            *ActionViewSet.basic_related_panels_general_admin,
            *ActionViewSet.progress_panels,
        ]),
        'dependency_role',
        # Relations that get a tab or panel of their own. Only their access rights are customizable;
        # `label_override` and `help_text_override` have no effect on them.
        'tasks',
        'contact_persons',
        'responsible_parties',
    ],
)

register_customizable_fields(
    ActionTask,
    [
        *collect_customizable_field_names(ActionViewSet.task_panels),
        # Relations edited in a panel of their own. As for the action-level relations above, only their
        # access rights are customizable; `label_override` and `help_text_override` have no effect.
        *TASK_ASSIGNMENT_RELATIONS,
    ],
)


@hooks.register('construct_snippet_action_menu')
def construct_snippet_action_menu(menu_items: list[ActionMenuItem], request: HttpRequest, context: dict[str, Any]):  # noqa: C901
    from wagtail.models import DraftStateMixin, LockableMixin, WorkflowMixin
    from wagtail.snippets import action_menu

    from actions.models.action import Action

    if context['model'] != Action:
        return

    model: type[Action] = context['model']
    instance: Action | None = context.get('instance')
    moderated = instance is not None and instance.plan.features.enable_moderation_workflow
    # Decides between "Save" and "Save draft"
    context['draftstate_enabled'] = moderated

    class RestartWorkflowMenuItem(action_menu.RestartWorkflowMenuItem):
        label = _('Resubmit for moderation')

    class CancelWorkflowMenuItem(action_menu.CancelWorkflowMenuItem):
        label = _('Cancel moderation')

    class PublishMenuItem(action_menu.PublishMenuItem):
        def is_shown(self, context) -> bool:
            user = user_or_bust(context['request'].user)
            instance = context['instance']
            return (
                super().is_shown(context) and user.can_publish_action(instance) and not instance.workflow_in_progress
            )  # If a workflow is in progress, use "approve" instead

    class SubmitForModerationMenuItem(action_menu.SubmitForModerationMenuItem):
        def is_shown(self, context) -> bool:
            if not super().is_shown(context):
                return False

            instance = context['instance']
            workflow_state = instance.current_workflow_state if instance else None
            in_moderation = workflow_state and workflow_state.status == workflow_state.STATUS_NEEDS_CHANGES

            workflow = instance.get_workflow()
            if workflow.tasks.count() > 1:
                """
                In multiple-task workflows, there needs to be a way for
                the moderator to initiate the workflow because otherwise
                the moderator has no way to pass the object along the
                workflow to the next moderation task.

                FIXME: optimally there would be a way for a moderator to
                start the workflow immediately from the second task if the
                editor hasn't initiated the first task. Now the moderator
                has to first submit, then approve if nobody has originally
                submitted.
                """
                return True

            if in_moderation:
                # Don't show "Resubmit" because then "Restart workflow" is what we probably want as it sends notifications to the
                # reviewers again.
                # FIXME: handle this in the multiple-task workflow case
                return False

            user = context['request'].user
            if user.can_approve_action(instance):
                # In one-task workflows, sending for moderation is redundant because they can publish immediately.
                return False
            return True

    class DeleteMenuItem(action_menu.ActionMenuItem):
        name = 'action-delete'
        label = _('Delete')
        icon_name = 'bin'

        def is_shown(self, context) -> bool:
            from wagtail.snippets.permissions import get_permission_name

            if context['view'] != 'edit' or context.get('locked_for_user'):
                return False
            user = context['request'].user
            if moderated:
                return user.has_perm(get_permission_name('delete', context['model']))
            policy = context['instance'].snippet_viewset.permission_policy
            return policy.user_has_permission_for_instance(user, 'delete', context['instance'])

        def get_url(self, context) -> str | None:
            instance = context['instance']
            url_name = instance.snippet_viewset.get_url_name('delete')
            return reverse(url_name, args=[quote(instance.pk)])

    for menu_item in list(menu_items):
        if type(menu_item) not in (
            action_menu.SaveMenuItem,
            action_menu.PublishMenuItem,
            action_menu.SubmitForModerationMenuItem,
            action_menu.RestartWorkflowMenuItem,
            action_menu.CancelWorkflowMenuItem,
            action_menu.UnpublishMenuItem,
        ):
            continue
        menu_items.remove(menu_item)

    # WorkflowMenuItem instances are inserted with order 100
    menu_items += [
        # SaveMenuItem(order=101),  # We want "Publish" (below) or "Approve" (100) as the default action (if shown)
        # FIXME: The previous line would cause "SaveMenuItem" to be not the first item, so the first item would
        # probably be a workflow-related item. This causes a problem because Wagtail in `workflow-action.js`
        # only appends hidden input elements to the form if the "more actions" dropdown is expanded. That is,
        # the default button must not be workflow-related. Otherwise Wagtail wouldn't handle the workflow
        # action properly. This should better be fixed in the Wagtail code, but until we find a good
        # solution, let's just live with a suboptimal menu item order.
        action_menu.SaveMenuItem(order=0),
        DeleteMenuItem(order=102),
    ]
    # Only plans with a moderation workflow have drafts, and with them publishing and locks
    if moderated and issubclass(model, DraftStateMixin):
        menu_items += [
            # UnpublishMenuItem(order=20),
            # PublishMenuItem(order=30),
            PublishMenuItem(order=5),
        ]
    if moderated and issubclass(model, WorkflowMixin):
        menu_items += [
            SubmitForModerationMenuItem(order=40),
            RestartWorkflowMenuItem(order=50),
            CancelWorkflowMenuItem(order=60),
        ]
    if moderated and issubclass(model, LockableMixin):
        menu_items.append(action_menu.LockedMenuItem(order=10000))

    for menu_item in list(menu_items):
        if not menu_item.is_shown(context):
            menu_items.remove(menu_item)
    menu_items.sort(key=lambda x: x.order)
    return


# If kausal_watch_extensions is installed, an extended version of the view set is registered there
if not find_spec('kausal_watch_extensions'):
    register_snippet(ActionViewSet)
