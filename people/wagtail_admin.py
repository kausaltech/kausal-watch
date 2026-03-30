# ruff: noqa: PLW2901
from __future__ import annotations

import logging
import typing
from datetime import timedelta
from typing import Any, cast

from django.contrib import admin
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.utils import display_for_value, quote
from django.contrib.admin.widgets import AdminFileWidget
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import Case, F, ManyToManyField, OneToOneRel, Prefetch, Q, When
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.forms import BooleanField, ChoiceField, ModelMultipleChoiceField
from django.urls import re_path
from django.utils import timezone
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, ObjectList, TabbedInterface

from dal import autocomplete
from wagtail_modeladmin.helpers.button import ButtonHelper
from wagtail_modeladmin.options import modeladmin_register
from wagtail_modeladmin.views import DeleteView

from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import naturaltime

from actions.models import ActionContactPerson, Plan, PlanPublicSiteViewer
from actions.perms import get_people_with_login_rights
from admin_site.utils import admin_req
from admin_site.wagtail import (
    ActivatePermissionHelperPlanContextModelAdminMixin,
    AplansAdminModelForm,
    AplansCreateView,
    AplansEditView,
    AplansIndexView,
    AplansModelAdmin,
    InitializeFormWithPlanMixin,
    InitializeFormWithUserMixin,
    PlanContextModelAdminPermissionHelper,
    get_translation_tabs,
)
from orgs.models import Organization, OrganizationPlanAdmin

from .models import Person
from .views import ImpersonateUserView, ResetPasswordView

if typing.TYPE_CHECKING:
    from datetime import date

    from django.contrib.admin.options import _DisplayT
    from django.http import HttpRequest
    from django_stubs_ext import StrOrPromise
    from wagtail.admin.panels import Panel

    from users.models import User


logger = logging.getLogger(__name__)


class IsContactPersonFilter(SimpleListFilter):
    title = _('Is contact person')
    parameter_name = 'contact_person'

    def lookups(self, request, model_admin):
        request = admin_req(request)
        plan = request.user.get_active_admin_plan()
        related_plans = Plan.objects.filter(pk=plan.pk) | plan.get_all_related_plans().all()
        # If there are related plans that have action contact persons, show a filter for each of these plans
        related_plans_contact_persons = ActionContactPerson.objects.filter(action__plan__in=related_plans)
        filter_plans = related_plans.filter(pk__in=related_plans_contact_persons.values_list('action__plan'))
        action_filters: list[tuple[str, StrOrPromise]]
        if filter_plans.exists():
            action_filters = [
                (f'action_in_plan__{plan.pk}', _('For an action in %(plan)s') % {'plan': plan.name_i18n}) for plan in filter_plans
            ]
        else:
            action_filters = [('action', _('For an action'))]
        choices = [
            *action_filters,
            ('peer_contact_persons', _('For same actions or indicators as me')),
            ('indicator', _('For an indicator')),
            ('none', _('Not a contact person')),
        ]
        return choices

    def queryset(self, request, queryset):
        user = cast('User', request.user)
        plan = user.get_active_admin_plan()
        queryset = queryset.prefetch_related(
            Prefetch('contact_for_actions', queryset=plan.actions.all(), to_attr='plan_contact_for_actions'),
        )
        queryset = queryset.prefetch_related(
            Prefetch('contact_for_indicators', queryset=plan.indicators.all(), to_attr='plan_contact_for_indicators'),
        )
        val = self.value()
        if val is None:
            return queryset
        if val == 'action':
            queryset = queryset.filter(contact_for_actions__in=plan.actions.all())
        elif val.startswith('action_in_plan__'):
            plan_pk = int(val[16:])
            queryset = queryset.filter(contact_for_actions__plan=plan_pk)
        elif val == 'indicator':
            queryset = queryset.filter(contact_for_indicators__in=plan.indicators.all())
        elif val == 'peer_contact_persons':
            person = user.person
            my_actions = plan.actions.filter(contact_persons__person=person)
            my_indicators = plan.indicators.filter(contact_persons__person=person)
            queryset = queryset.filter(
                Q(contact_for_actions__pk__in=my_actions) | Q(contact_for_indicators__pk__in=my_indicators),
            )
        else:
            queryset = queryset.exclude(contact_for_actions__in=plan.actions.all()).exclude(
                contact_for_indicators__in=plan.indicators.all()
            )
        return queryset.distinct()


def smart_truncate(content, length=100, suffix='...'):
    if len(content) <= length:
        return content
    return ' '.join(content[: length + 1].split(' ')[0:-1]) + suffix


class AvatarWidget(AdminFileWidget):
    template_name = 'kausal_common/people/avatar_widget.html'


class PersonForm(AplansAdminModelForm[Person]):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        self.user = kwargs.pop('user')
        instance = kwargs['instance']  # should be a model instance (perhaps with pk None) due to ModelFormView
        initial = kwargs.setdefault('initial', {})
        if instance.pk is None:
            initial.setdefault('organization', self.plan.organization)
        else:
            initial['is_admin_for_active_plan'] = self.plan in instance.general_admin_plans.all()
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.created_by = self.user

    def save(self, commit=True):
        if 'image' in self.files:
            self.instance.image_cropping = None
        return super().save(commit)


class PersonFormForGeneralAdmin(PersonForm):
    class AccessLevel(models.TextChoices):
        PUBLIC_SITE_ONLY = 'public_site_only', _('Access to public site only')
        FULL_ACCESS = 'full_access', _('Access to admin site and public site')

    is_admin_for_active_plan = BooleanField(required=False, label=_('Is plan admin'))
    access_level = ChoiceField(choices=AccessLevel.choices, required=True, label=_('Site access'))
    organization_plan_admin_orgs: ModelMultipleChoiceField[Organization] = ModelMultipleChoiceField(
        queryset=None,
        required=False,
        widget=autocomplete.ModelSelect2Multiple(url='organization-autocomplete'),
        label=_('Plan admin organizations'),
    )

    def __init__(self, *args, **kwargs):
        plan = kwargs['plan']
        instance = kwargs['instance']  # should be a model instance (perhaps with pk None) due to ModelFormView
        initial = kwargs.setdefault('initial', {})
        initial['access_level'] = self.AccessLevel.FULL_ACCESS
        if instance.pk is not None:
            initial['organization_plan_admin_orgs'] = instance.organization_plan_admins.filter(plan=plan).values_list(
                'organization', flat=True
            )
            is_public_site_viewer = instance.plans_with_public_site_access.filter(plan=plan).exists()
            initial['access_level'] = self.AccessLevel.PUBLIC_SITE_ONLY if is_public_site_viewer else self.AccessLevel.FULL_ACCESS

        super().__init__(*args, **kwargs)
        assert self.user.is_general_admin_for_plan(self.plan)
        if plan.features.allow_public_site_login:
            if initial.get('access_level') == self.AccessLevel.PUBLIC_SITE_ONLY:
                del self.fields['organization_plan_admin_orgs']
                del self.fields['is_admin_for_active_plan']
                del self.fields['contact_for_actions_unordered']
                del self.fields['participated_in_training']
        elif initial.get('access_level') != self.AccessLevel.PUBLIC_SITE_ONLY:
            # Allow removing lingering public site restriction if public site login was recently removed
            del self.fields['access_level']
        if 'organization_plan_admin_orgs' in self.fields:
            cast('ModelMultipleChoiceField[Any]', self.fields['organization_plan_admin_orgs']).queryset = (
                Organization.objects.get_queryset().available_for_plan(self.plan).filter(dissolution_date=None)
            )

    def clean(self):
        cleaned_data = super().clean()
        assert cleaned_data is not None
        access_level = cleaned_data.get('access_level')
        is_plan_admin = cleaned_data.get('is_admin_for_active_plan')
        organization_plan_admin_orgs = cleaned_data.get('organization_plan_admin_orgs')
        contact_for_actions = cleaned_data.get('contact_for_actions_unordered')
        if access_level == self.AccessLevel.PUBLIC_SITE_ONLY:  # noqa: SIM102
            if is_plan_admin or organization_plan_admin_orgs or contact_for_actions:
                raise ValidationError(
                    'Person cannot have admin responsibilities while also being restricted to only public site access.',
                )
        return cleaned_data

    def save(self, commit=True):
        instance = super().save(commit)
        is_admin_for_active_plan = self.cleaned_data.get('is_admin_for_active_plan')
        access_level = self.cleaned_data.get('access_level')
        if access_level == self.AccessLevel.PUBLIC_SITE_ONLY:
            PlanPublicSiteViewer.objects.get_or_create(plan=self.plan, person=instance)
        elif access_level == self.AccessLevel.FULL_ACCESS:
            PlanPublicSiteViewer.objects.filter(plan=self.plan, person=instance).delete()
        if is_admin_for_active_plan is True:
            instance.general_admin_plans.add(self.plan)
        elif is_admin_for_active_plan is False:
            instance.general_admin_plans.remove(self.plan)

        organization_plan_admin_orgs = self.cleaned_data.get('organization_plan_admin_orgs')
        if organization_plan_admin_orgs is not None:
            with transaction.atomic():
                OrganizationPlanAdmin.objects.filter(plan=self.plan, person=instance).delete()
                for org in organization_plan_admin_orgs:
                    OrganizationPlanAdmin.objects.create(organization=org, plan=self.plan, person=instance)
        return instance


class PersonCreateView(
    ActivatePermissionHelperPlanContextModelAdminMixin[Person],
    InitializeFormWithPlanMixin[Person],
    InitializeFormWithUserMixin[Person],
    AplansCreateView[Person],
):
    def form_valid(self, form, *args, **kwargs):
        # Make sure form only contains is_admin_for_active_plan
        # TODO: Also do this for organization_plan_admin_orgs?
        user = cast('User', self.request.user)
        plan = user.get_active_admin_plan()
        is_general_admin = user.is_general_admin_for_plan(plan)
        contains_admin_flag = form.cleaned_data.get('is_admin_for_active_plan') is not None

        def iff(a, b) -> bool:
            return (a and b) or (not a and not b)

        assert iff(contains_admin_flag, is_general_admin)
        return super().form_valid(form, *args, **kwargs)


class PersonEditView(InitializeFormWithPlanMixin[Person], InitializeFormWithUserMixin[Person], AplansEditView[Person]):
    pass


class PersonIndexView(AplansIndexView[Person]):
    def get_ordering(self, request, queryset):
        ret = super().get_ordering(request, queryset)
        out = []
        for order in ret:
            field = order
            if order[0] == '-':
                field = field[1:]
                desc = True
            else:
                desc = False
            if field != 'user__last_login':
                out.append(order)
                continue
            order = F('user__last_login')
            if desc:
                order = order.desc(nulls_last=True)
            else:
                order = order.asc(nulls_first=True)
            out.append(order)
        return out


class PersonPermissionHelper(PlanContextModelAdminPermissionHelper[Person]):
    _org_map: dict[int, Organization] | None

    def __init__(self, model: type[Person], inspect_view_enabled=False):
        self._org_map = None
        super().__init__(model, inspect_view_enabled)

    def prefetch_cache(self):
        if self.plan is None:
            return
        org_qs = Organization.objects.get_queryset().available_for_plan(self.plan)
        self._org_map = {org.id: org for org in org_qs}

    def clean_cache(self):
        self._org_map = None

    def user_can_edit_obj(self, user: User, obj: Person):
        if not super().user_can_edit_obj(user, obj):
            return False
        # Users can always edit themselves
        if obj.user == user:
            return True
        return user.can_edit_or_delete_person_within_plan(
            obj,
            plan=self.plan,
            orgs=self._org_map,
        )

    def user_can_delete_obj(self, user, obj: Person):
        if not super().user_can_delete_obj(user, obj):
            return False
        return user.can_edit_or_delete_person_within_plan(
            obj,
            plan=self.plan,
            orgs=self._org_map,
        )

    def user_can_create(self, user: User):
        if user.is_general_admin_for_plan(self.plan):
            return True
        person = user.get_corresponding_person()
        # FIXME: there is some hardcoding of assumptions about contact person roles here.
        # These should be moved to a role-based system.
        if (
            not ActionContactPerson.objects
            .filter(action__plan=self.plan)
            .filter(person=person)
            .exclude(role=ActionContactPerson.Role.EDITOR)
        ):
            # Only persons with role other than editor can add persons
            return False
        return super().user_can_create(user)


def _person_can_access_admin(person) -> bool:
    return person.pk in get_people_with_login_rights()


class PersonButtonHelper(ButtonHelper):
    def delete_button(self, *args, **kwargs):
        button = super().delete_button(*args, **kwargs)
        button['label'] = _('Deactivate')
        return button

    def reset_password_button(self, pk, **kwargs):
        """Button for sending password reset emails and displaying reset tokens."""
        return {
            'label': _('Reset password'),
            'title': _('Create a password reset link'),
            'url': self.url_helper.get_action_url('reset_password', quote(pk)),
            'classname': self.finalise_classname(['button-secondary', 'button-small']),
        }

    def impersonation_button(self, pk, **kwargs):
        return {
            'label': _('View as user'),
            'title': _('View site as it looks for this user'),
            'url': self.url_helper.get_action_url('view_as_user', quote(pk)),
            'classname': self.finalise_classname(['button-secondary', 'button-small']),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        assert isinstance(obj, Person)
        # Only display a password reset button if the user has a usable password. This prevents showing the button for
        # users from a customer that uses SSO because such users normally don't have a usable password.
        target_has_password = obj.user and obj.user.has_usable_password()
        target_is_admin_of_any_plan = obj.user and obj.user.is_general_admin_for_plan()
        # TODO: Should be harmonized with ResetPasswordView.check_action_permitted()
        if user.is_general_admin_for_plan(plan) and target_has_password and not target_is_admin_of_any_plan:
            reset_password_button = self.reset_password_button(
                pk=getattr(obj, self.opts.pk.attname),
                **kwargs,
            )
            buttons.append(reset_password_button)
        if user.is_superuser and obj.user != user and _person_can_access_admin(obj):
            impersonation_button = self.impersonation_button(
                pk=getattr(obj, self.opts.pk.attname),
                **kwargs,
            )
            buttons.append(impersonation_button)
        return buttons


class PersonDeleteView(ActivatePermissionHelperPlanContextModelAdminMixin[Person], DeleteView[Person]):
    instance: Person
    model: type[Person]

    def get(self, request, *args, **kwargs):
        linked_objects = []
        fields = self.model._meta.fields_map.values()
        rel_fields = (obj for obj in fields if isinstance(obj, ForeignObjectRel) and not isinstance(obj.field, ManyToManyField))
        for rel in rel_fields:
            obj = None
            key: str | None
            if isinstance(rel, OneToOneRel):
                key = rel.get_accessor_name()
                try:
                    if key:
                        obj = getattr(self.instance, key)
                except ObjectDoesNotExist:
                    pass
                else:
                    if obj:
                        linked_objects.append(obj)
            else:
                key = rel.get_accessor_name()
                if key:
                    qs = getattr(self.instance, key)
                    for obj in qs.all():
                        linked_objects.append(obj)  # noqa: PERF402
        context = self.get_context_data(
            protected_error=True,
            linked_objects=linked_objects,
        )
        return self.render_to_response(context)

    def confirmation_message(self):
        return _('Are you sure you want to deactivate this person?')

    def delete_instance(self):
        # FIXME: Duplicated in actions.api.PersonViewSet.perform_destroy()
        acting_admin_user = self.request.user
        self.instance.delete_and_deactivate_corresponding_user(acting_admin_user)


class PersonAdmin(AplansModelAdmin[Person]):
    model = Person
    create_view_class = PersonCreateView
    edit_view_class = PersonEditView
    index_view_class = PersonIndexView
    delete_view_class = PersonDeleteView
    delete_template_name = 'people/delete.html'
    permission_helper_class = PersonPermissionHelper
    menu_icon = 'user'
    menu_label = _('People')
    menu_order = 210
    exclude_from_explorer = False
    search_fields = ('first_name', 'last_name', 'title', 'organization__name', 'organization__abbreviation')
    list_filter = (IsContactPersonFilter,)
    button_helper_class = PersonButtonHelper
    index_view_extra_css = ['css/modeladmin-index.css']
    permission_helper: PersonPermissionHelper

    def get_permission_helper_class(self):
        return super().get_permission_helper_class()

    def get_queryset(self, request: HttpRequest):
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        qs = super().get_queryset(request).available_for_plan(plan).select_related('user')
        if user.is_general_admin_for_plan(plan):
            qs = qs.annotate(
                is_plan_admin=Case(
                    When(id__in=plan.general_admins.all(), then=True),
                    default=False,
                )
            )
        return qs

    def get_empty_value_display(self, field=None):
        if getattr(field, '_name', field) == 'last_logged_in':
            return display_for_value(value=False, empty_value_display='', boolean=True)
        return super().get_empty_value_display(field)

    def get_list_display(self, request: HttpRequest):  # noqa: C901
        # get_list_display() gets called a lot, so we cache the results
        if hasattr(request, '_person_list_display'):
            return getattr(request, '_person_list_display')  # noqa: B009

        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()

        # We use a cached and path-indexed version of all organizations to reduce
        # SQL queries.
        all_orgs = list(Organization.objects.get_queryset().available_for_plan(plan))
        orgs_by_path = Organization.make_orgs_by_path(all_orgs)
        orgs_by_id = {org.id: org for org in all_orgs}

        def edit_url(obj: Person) -> str | None:
            if self.permission_helper.user_can_edit_obj(user, obj):
                return self.url_helper.get_action_url('edit', obj.pk)
            return None

        @admin.display(description='', empty_value='')
        def avatar(obj: Person) -> str:
            avatar_url = obj.get_avatar_url(request, size='50x50')
            if not avatar_url:
                return ''
            img = format_html('<span class="avatar"><img src="{}" /></span>', avatar_url)
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, img)
            return img

        @admin.display(description='', empty_value='')
        def cannot_access_admin_warning(obj: Person) -> str:
            if not _person_can_access_admin(obj):
                tooltip = _(
                    'This person has no access to the admin interface. This is commonly because no actions or '
                    'indicators are assigned to them.',
                )
                return format_html(
                    '<span data-controller="w-tooltip" data-w-tooltip-content-value="{}" style="cursor: pointer;">'
                    '<svg class="icon icon-warning" style="height: 1.5em; width: 1.5em;" aria-hidden="true">'
                    '<use href="#icon-warning"></use>'
                    '</svg>'
                    '</span>',
                    tooltip,
                )
            return ''

        @admin.display(description=_('first name'), ordering='first_name')
        def first_name(obj: Person) -> str:
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, obj.first_name)
            return obj.first_name

        @admin.display(description=_('last name'), ordering='last_name')
        def last_name(obj: Person) -> str:
            url = edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, obj.last_name)
            return obj.last_name

        @admin.display(description=_('organization'), ordering='organization__name')
        def organization(obj: Person) -> str:
            org_id = obj.organization_id
            org = orgs_by_id.get(org_id, obj.organization)
            return org.get_fully_qualified_name(orgs_by_path=orgs_by_path)

        fields: list[_DisplayT[Person]] = [avatar, cannot_access_admin_warning, first_name, last_name, 'title', organization]
        # fields = [avatar, first_name, last_name, 'title', organization]

        @admin.display(description=_('last login'), ordering='user__last_login')
        def last_logged_in(obj: Person) -> str | date | None:
            user = obj.user
            if not user or not user.last_login:
                return None
            now = timezone.now()
            delta = now - user.last_login
            if delta > timedelta(days=30):
                return user.last_login.date()
            return naturaltime(delta)

        setattr(last_logged_in, '_name', 'last_logged_in')  # noqa: B010

        if user.is_general_admin_for_plan(plan):

            @admin.display(description=_('Is plan admin'), ordering='-is_plan_admin', boolean=True)
            def is_plan_admin(obj: Person) -> bool:
                return obj.is_plan_admin  # type: ignore[attr-defined]

            setattr(is_plan_admin, '_name', 'is_plan_admin')  # noqa: B010
            fields.append(is_plan_admin)

            fields.append(last_logged_in)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
            fields.append('participated_in_training')

        @admin.display(description=_('contact for actions'))
        def contact_for_actions(obj) -> str:
            return '; '.join([smart_truncate(str(act), 40) for act in obj.plan_contact_for_actions])

        @admin.display(description=_('contact for indicators'))
        def contact_for_indicators(obj) -> str:
            return '; '.join([smart_truncate(str(ind), 40) for ind in obj.plan_contact_for_indicators])

        contact_person_filter = request.GET.get('contact_person', '')
        if contact_person_filter == 'action':
            fields.append(contact_for_actions)
        elif contact_person_filter == 'indicator':
            fields.append(contact_for_indicators)

        setattr(request, '_person_list_display', fields)  # noqa: B010
        return fields

    basic_panels = [
        FieldPanel('first_name'),
        FieldPanel('last_name'),
        FieldPanel('email'),
        FieldPanel('title'),
        FieldPanel(
            'organization',
            widget=autocomplete.ModelSelect2(url='organization-autocomplete'),
        ),
        FieldPanel('image', widget=AvatarWidget),
    ]

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()
        basic_panels = list(self.basic_panels)
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            form_class = PersonFormForGeneralAdmin
            basic_panels.append(FieldPanel('access_level'))
            basic_panels.append(FieldPanel('participated_in_training'))
            basic_panels.append(FieldPanel('is_admin_for_active_plan'))
            basic_panels.append(
                FieldPanel(
                    'organization_plan_admin_orgs',
                    widget=autocomplete.ModelSelect2Multiple(url='organization-autocomplete'),
                )
            )
            # FIXME: This saves ActionContactPerson instances without specifying `order`, which leads to duplicates of
            # the default value.
            # TODO: No way to specify `primary_contact`.
            # Recall that we tried using inline panels (changing the other ForeignKey in the model to a ParentalKey and
            # adding some workarounds) for `actioncontactperson_set`, but came across the problem that it screws up the
            # ordering because the order as displayed in the person admin view is not what we want -- the order we want
            # should rather be the one as specified in the action edit view.
            basic_panels.append(
                FieldPanel(
                    'contact_for_actions_unordered',
                    widget=autocomplete.ModelSelect2Multiple(url='action-autocomplete'),
                )
            )
        else:
            form_class = PersonForm

        tabs: list[Panel[Any]] = [ObjectList(basic_panels, heading=_('General'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return TabbedInterface(tabs, base_form_class=form_class)

    def get_extra_attrs_for_row(self, obj, context):
        assert isinstance(obj, Person)
        if not _person_can_access_admin(obj):
            # Add CSS class to highlight rows of users without admin access
            return {
                'class': 'warning-row',
            }
        return {}

    def reset_password_view(self, request, instance_pk):
        """Generate a class-based view to provide 'reset password' functionality."""
        return ResetPasswordView.as_view(model_admin=self, target_person_pk=instance_pk)(request)

    def impersonation_view(self, request, instance_pk):
        return ImpersonateUserView.as_view(model_admin=self, target_person_pk=instance_pk)(request)

    def get_admin_urls_for_registration(self):
        """Add the new url for reset password page to the registered URLs."""
        urls = super().get_admin_urls_for_registration()
        reset_password_url = re_path(
            self.url_helper.get_action_url_pattern('reset_password'),
            self.reset_password_view,
            name=self.url_helper.get_action_url_name('reset_password'),
        )
        impersonation_url = re_path(
            self.url_helper.get_action_url_pattern('view_as_user'),
            self.impersonation_view,
            name=self.url_helper.get_action_url_name('view_as_user'),
        )
        return urls + (
            reset_password_url,
            impersonation_url,
        )


modeladmin_register(PersonAdmin)
