from __future__ import annotations

import logging
import typing
from datetime import timedelta
from typing import Any, TypedDict, cast

from django.contrib.admin.utils import display_for_value, quote
from django.contrib.admin.widgets import AdminFileWidget
from django.core.exceptions import ObjectDoesNotExist, ValidationError
from django.db import models, transaction
from django.db.models import Exists, F, ManyToManyField, Model, OneToOneRel, OuterRef, Prefetch, Q
from django.db.models.fields.reverse_related import ForeignObjectRel
from django.forms import BooleanField, ChoiceField, ModelMultipleChoiceField
from django.template.loader import render_to_string
from django.templatetags.static import static
from django.urls import path, reverse
from django.utils import timezone
from django.utils.functional import cached_property
from django.utils.html import format_html, format_html_join
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _
from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.panels import FieldPanel, ObjectList, TabbedInterface
from wagtail.admin.ui.tables import BooleanColumn, Column, Table
from wagtail.log_actions import log
from wagtail.snippets.models import register_snippet

import django_filters
from dal import autocomplete

from kausal_common.users import user_or_bust

from aplans.utils import naturaltime

from actions.category_admin import PanelFormMixin
from actions.models import ActionContactPerson, GeneralPlanAdmin, Plan, PlanPublicSiteViewer
from actions.perms import get_people_with_login_rights
from admin_site.mixins import ActivatePermissionHelperPlanContextMixin
from admin_site.viewsets import (
    InstancePermissionCheckedMixin,
    WatchCreateView,
    WatchDeleteView,
    WatchEditView,
    WatchIndexView,
    WatchViewSet,
)
from admin_site.wagtail import AplansAdminModelForm, get_translation_tabs
from indicators.models import IndicatorContactPerson
from orgs.models import Organization, OrganizationPlanAdmin

from .models import Person
from .views import ImpersonateUserView, ResetPasswordView

if typing.TYPE_CHECKING:
    from datetime import date

    from django.http import HttpRequest
    from django.utils.functional import _StrOrPromise as StrOrPromise
    from wagtail.admin.panels import Panel

    from users.models import User

    from .models import PersonQuerySet


logger = logging.getLogger(__name__)


class PersonRole(models.TextChoices):
    PLAN_ADMIN = 'plan_admin', _('Plan admin')
    ORGANIZATION_ADMIN = 'organization_admin', _('Organization admin')
    CONTACT_PERSON = 'contact_person', _('Contact person')
    VIEWER = 'viewer', _('Viewer')


# The queryset annotation that tells whether a listed person holds the role in the active plan
PERSON_ROLE_ANNOTATIONS: dict[PersonRole, str] = {
    PersonRole.PLAN_ADMIN: 'is_plan_admin',
    PersonRole.ORGANIZATION_ADMIN: 'is_organization_admin',
    PersonRole.CONTACT_PERSON: 'is_contact_person',
    PersonRole.VIEWER: 'is_viewer',
}


def annotate_person_roles(qs: PersonQuerySet, plan: Plan) -> PersonQuerySet:
    person = OuterRef('pk')
    is_action_contact = Exists(ActionContactPerson.objects.filter(action__plan=plan, person=person))
    is_indicator_contact = Exists(IndicatorContactPerson.objects.filter(indicator__in=plan.indicators.all(), person=person))
    return qs.annotate(
        is_plan_admin=Exists(GeneralPlanAdmin.objects.filter(plan=plan, person=person)),
        is_organization_admin=Exists(OrganizationPlanAdmin.objects.filter(plan=plan, person=person)),
        is_contact_person=Q(is_action_contact) | Q(is_indicator_contact),
        is_viewer=Exists(PlanPublicSiteViewer.objects.filter(plan=plan, person=person)),
    )


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
            self.instance.image_cropping = None  # type: ignore[assignment]
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
        # Public-site access is available for every plan, so the access level is always offered.
        if initial.get('access_level') == self.AccessLevel.PUBLIC_SITE_ONLY:
            del self.fields['organization_plan_admin_orgs']
            del self.fields['is_admin_for_active_plan']
            del self.fields['contact_for_actions_unordered']
            del self.fields['participated_in_training']
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
        if contact_for_actions is not None:
            contact_for_actions = contact_for_actions.filter(plan=self.plan)
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


PERSON_BASIC_PANELS: list[Panel[Any]] = [
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


class PersonFormKwargsMixin:
    request: HttpRequest

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), 'user': self.request.user}  # type: ignore[misc]


def get_person_panel(request: HttpRequest, instance: Person) -> TabbedInterface:
    basic_panels = list(PERSON_BASIC_PANELS)
    user = user_or_bust(request.user)
    plan = user.get_active_admin_plan()
    if user.is_general_admin_for_plan(plan):
        form_class: type[PersonForm] = PersonFormForGeneralAdmin
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
    tabs += get_translation_tabs(instance, request)
    return TabbedInterface(tabs, base_form_class=form_class).bind_to_model(Person)


class PersonCreateView(ActivatePermissionHelperPlanContextMixin, PersonFormKwargsMixin, PanelFormMixin, WatchCreateView[Person]):
    def get_panel(self):
        instance = Person()
        self.initialize_instance(self.request, instance)
        return get_person_panel(self.request, instance)

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


class PersonEditView(InstancePermissionCheckedMixin, PersonFormKwargsMixin, PanelFormMixin, WatchEditView[Person]):
    def get_panel(self):
        return get_person_panel(self.request, self.object)


def _person_can_access_admin(person) -> bool:
    return person.pk in get_people_with_login_rights()


def _warn_about_missing_admin_access(person: Person, plan: Plan) -> bool:
    # A viewer who got in through an access request is only meant to see the public site
    if plan.features.enable_access_requests and person.is_viewer:  # type: ignore[attr-defined]
        return False
    return not _person_can_access_admin(person)


def _get_orgs_for_listing(plan) -> list[Organization]:
    all_orgs = list(Organization.objects.get_queryset().available_for_plan(plan))
    ancestor_paths: set[str] = set()
    for org in all_orgs:
        ancestor_paths.update(org.path[:pos] for pos in range(org.steplen, len(org.path), org.steplen))
    if ancestor_paths:
        seen = {o.pk for o in all_orgs}
        all_orgs.extend(Organization.objects.filter(path__in=ancestor_paths).exclude(pk__in=seen))
    return all_orgs


class PersonRoleFilterSet(WagtailFilterSet):
    NO_ROLE = 'none'

    role = django_filters.ChoiceFilter(
        label=_('Role'),
        choices=[*PersonRole.choices, (NO_ROLE, _('No role'))],
        method='filter_role',
    )

    class Meta:
        model = Person
        fields: list[str] = []

    def filter_role(self, queryset, name, value):
        if value == self.NO_ROLE:
            return queryset.filter(**dict.fromkeys(PERSON_ROLE_ANNOTATIONS.values(), False))
        return queryset.filter(**{PERSON_ROLE_ANNOTATIONS[PersonRole(value)]: True})


class RowButton(TypedDict):
    url: str
    label: StrOrPromise
    title: StrOrPromise


class PersonTable(Table):
    plan: Plan

    class Media:
        css = {'all': ('css/modeladmin-index.css',)}

    def get_row_classname(self, instance: Person) -> str:
        if _warn_about_missing_admin_access(instance, self.plan):
            # Highlight rows of users without admin access
            return 'warning-row'
        return ''


class HTMLColumn(Column):
    """A column whose accessor returns HTML, with an empty cell for `None`."""

    def get_value(self, instance):
        value = super().get_value(instance)
        return '' if value is None else value


class PersonIndexView(WatchIndexView[Person]):
    table_class = PersonTable

    @cached_property
    def plan(self) -> Plan:
        return user_or_bust(self.request.user).get_active_admin_plan()

    def get_table(self, object_list):
        table = super().get_table(object_list)
        table.plan = self.plan
        return table

    def _user_has_permission_for(self, action: str, instance: Person) -> bool:
        assert self.permission_policy is not None
        return self.permission_policy.user_has_permission_for_instance(self.request.user, action, instance)

    def get_edit_url(self, instance: Person):
        if not self._user_has_permission_for('change', instance):
            return None
        return super().get_edit_url(instance)

    def get_delete_url(self, instance: Person):
        if not self._user_has_permission_for('delete', instance):
            return None
        return super().get_delete_url(instance)

    def _get_row_buttons(self, instance: Person) -> list[RowButton]:
        buttons: list[RowButton] = []
        if edit_url := self.get_edit_url(instance):
            buttons.append({'url': edit_url, 'label': _('Edit'), 'title': _('Edit this person')})
        if delete_url := self.get_delete_url(instance):
            buttons.append({'url': delete_url, 'label': _('Deactivate'), 'title': _('Deactivate this person')})
        user = user_or_bust(self.request.user)
        # Only display a password reset button if the user has a usable password. This prevents showing the button for
        # users from a customer that uses SSO because such users normally don't have a usable password.
        target_has_password = instance.user and instance.user.has_usable_password()
        target_is_admin_of_any_plan = instance.user and instance.user.is_general_admin_for_plan()
        # TODO: Should be harmonized with ResetPasswordView.check_action_permitted()
        if user.is_general_admin_for_plan(self.plan) and target_has_password and not target_is_admin_of_any_plan:
            buttons.append({
                'url': reverse('wagtailsnippets_people_person:reset_password', args=[quote(instance.pk)]),
                'label': _('Reset password'),
                'title': _('Create a password reset link'),
            })
        if user.is_superuser and instance.user != user and _person_can_access_admin(instance):
            buttons.append({
                'url': reverse('wagtailsnippets_people_person:view_as_user', args=[quote(instance.pk)]),
                'label': _('View as user'),
                'title': _('View site as it looks for this user'),
            })
        return buttons

    @cached_property
    def columns(self):  # type: ignore[override]  # noqa: C901
        user = user_or_bust(self.request.user)
        plan = self.plan
        request = self.request

        # We use a cached and path-indexed version of all organizations to reduce
        # SQL queries. Ancestors are pulled in so get_fully_qualified_name can
        # resolve parent paths even when an ancestor isn't itself in
        # `available_for_plan` (e.g., a suborg is plan-related but its parent isn't).
        all_orgs = _get_orgs_for_listing(plan)
        orgs_by_path = Organization.make_orgs_by_path(all_orgs)
        orgs_by_id = {org.id: org for org in all_orgs}

        def link_to_edit(obj: Person, content: str) -> str:
            url = self.get_edit_url(obj)
            if url:
                return format_html('<a href="{}">{}</a>', url, content)
            return content

        def avatar(obj: Person) -> str:
            # Viewers stand out with their own placeholder even when they have uploaded an image
            if obj.is_viewer:  # type: ignore[attr-defined]
                img = format_html(
                    '<span class="avatar"><img src="{}" alt="{}" title="{}" /></span>',
                    static('people/avatar-viewer-placeholder.svg'),
                    PersonRole.VIEWER.label,
                    PersonRole.VIEWER.label,
                )
            else:
                avatar_url = obj.get_avatar_url(request, size='50x50') or static('people/avatar-placeholder.svg')
                img = format_html('<span class="avatar"><img src="{}" /></span>', avatar_url)
            return link_to_edit(obj, img)

        def cannot_access_admin_warning(obj: Person) -> str:
            if not _warn_about_missing_admin_access(obj, plan):
                return ''
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

        def organization(obj: Person) -> str:
            org = orgs_by_id.get(obj.organization_id, obj.organization)
            return org.get_fully_qualified_name(orgs_by_path=orgs_by_path)

        def role(obj: Person) -> str:
            roles = [r for r, annotation in PERSON_ROLE_ANNOTATIONS.items() if getattr(obj, annotation)]
            return format_html_join(
                '', '<span class="w-status person-role person-role--{}">{}</span>', ((r.value, r.label) for r in roles)
            )

        def last_logged_in(obj: Person) -> str | date:
            user = obj.user
            if not user or not user.last_login:
                return display_for_value(value=False, empty_value_display='', boolean=True)
            delta = timezone.now() - user.last_login
            if delta > timedelta(days=30):
                return user.last_login.date()
            return naturaltime(delta)

        def actions(obj: Person) -> str:
            return render_to_string('people/person_actions_menu.html', {'buttons': self._get_row_buttons(obj)}, request=request)

        columns: list[Column] = [
            HTMLColumn('avatar', label='', accessor=avatar),
            HTMLColumn('cannot_access_admin_warning', label='', accessor=cannot_access_admin_warning),
            HTMLColumn('email', label=_('email address'), sort_key='email', accessor=lambda obj: link_to_edit(obj, obj.email)),
            HTMLColumn(
                'first_name',
                label=_('first name'),
                sort_key='first_name',
                accessor=lambda obj: link_to_edit(obj, obj.first_name),
            ),
            HTMLColumn(
                'last_name', label=_('last name'), sort_key='last_name', accessor=lambda obj: link_to_edit(obj, obj.last_name)
            ),
            HTMLColumn('title', label=capfirst(Person._meta.get_field('title').verbose_name), sort_key='title'),
            HTMLColumn('organization', label=_('organization'), sort_key='organization__name', accessor=organization),
            HTMLColumn('role', label=_('Role'), sort_key='role', accessor=role),
        ]
        if user.is_general_admin_for_plan(plan):
            columns.append(
                HTMLColumn('last_logged_in', label=_('last login'), sort_key='user__last_login', accessor=last_logged_in)
            )
            columns.append(
                BooleanColumn(
                    'attended_training',
                    # The header wraps onto two lines to keep the column narrow
                    label=format_html('<span class="person-listing-wrapped-header">{}</span>', _('Attended training')),
                    sort_key='participated_in_training',
                    accessor='participated_in_training',
                )
            )
        if request.GET.get('role') == PersonRole.CONTACT_PERSON:
            columns.append(
                HTMLColumn(
                    'contact_for_actions',
                    label=_('contact for actions'),
                    accessor=lambda obj: '; '.join([smart_truncate(str(act), 40) for act in obj.plan_contact_for_actions]),
                )
            )
            columns.append(
                HTMLColumn(
                    'contact_for_indicators',
                    label=_('contact for indicators'),
                    accessor=lambda obj: '; '.join([smart_truncate(str(ind), 40) for ind in obj.plan_contact_for_indicators]),
                )
            )
        # The rarely used row actions live in a menu instead of the buttons shown on hover
        columns.append(
            HTMLColumn('actions', label=format_html('<span class="w-sr-only">{}</span>', _('Actions')), accessor=actions)
        )
        return columns

    def search_queryset(self, queryset):
        # Every word has to match one of the fields, as in the ModelAdmin
        if not self.is_searching:
            return queryset
        for word in (self.search_query or '').split():
            query = Q()
            for field in self.search_fields or []:
                query |= Q(**{f'{field}__icontains': word})
            queryset = queryset.filter(query)
        return queryset

    def order_queryset(self, queryset):
        # People who never logged in sort last when sorting by the newest login, and first otherwise
        if self.ordering == '-user__last_login':
            return queryset.order_by(F('user__last_login').desc(nulls_last=True))
        if self.ordering == 'user__last_login':
            return queryset.order_by(F('user__last_login').asc(nulls_first=True))
        if self.ordering == 'role':
            return queryset.order_by('-is_plan_admin')
        if self.ordering == '-role':
            return queryset.order_by('is_plan_admin')
        return super().order_queryset(queryset)


class PersonDeleteView(ActivatePermissionHelperPlanContextMixin, WatchDeleteView[Person]):
    def get_linked_objects(self) -> list[tuple[str, Model]]:
        linked_objects: list[Model] = []
        fields = Person._meta.fields_map.values()
        rel_fields = (obj for obj in fields if isinstance(obj, ForeignObjectRel) and not isinstance(obj.field, ManyToManyField))
        for rel in rel_fields:
            obj = None
            key = rel.get_accessor_name()
            if not key:
                continue
            if isinstance(rel, OneToOneRel):
                try:
                    obj = getattr(self.object, key)
                except ObjectDoesNotExist:
                    pass
                else:
                    if obj:
                        linked_objects.append(obj)
            else:
                linked_objects.extend(getattr(self.object, key).all())
        return [(str(capfirst(obj._meta.verbose_name)), obj) for obj in linked_objects]

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), 'linked_objects': self.get_linked_objects()}

    @property
    def confirmation_message(self):
        return _('Are you sure you want to deactivate this person?')

    def delete_action(self):
        # FIXME: Duplicated in actions.api.PersonViewSet.perform_destroy()
        with transaction.atomic():
            log(instance=self.object, action='wagtail.delete')
            self.object.delete_and_deactivate_corresponding_user(self.request.user)


class PersonViewSet(WatchViewSet[Person]):
    model = Person
    icon = 'user'
    menu_label = _('People')
    menu_order = 210
    add_to_admin_menu = True
    url_prefix = 'people/person'
    search_fields = ['first_name', 'last_name', 'title', 'organization__name', 'organization__abbreviation']
    # Search the database like the ModelAdmin did, as the search index cannot search the organization names
    search_backend_name = None
    filterset_class = PersonRoleFilterSet
    list_per_page = 100
    bulk_delete_enabled = False
    index_view_class = PersonIndexView
    add_view_class = PersonCreateView
    edit_view_class = PersonEditView
    delete_view_class = PersonDeleteView
    delete_template_name = 'people/delete.html'

    edit_handler = ObjectList(PERSON_BASIC_PANELS, base_form_class=PersonForm)

    def get_queryset(self, request: HttpRequest):
        plan = user_or_bust(request.user).get_active_admin_plan()
        qs = Person.objects.qs.available_for_plan(plan).select_related('user')
        qs = qs.prefetch_related(
            Prefetch('contact_for_actions', queryset=plan.actions.all(), to_attr='plan_contact_for_actions'),
            Prefetch('contact_for_indicators', queryset=plan.indicators.all(), to_attr='plan_contact_for_indicators'),
        )
        return annotate_person_roles(qs, plan)

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path('reset_password/<str:instance_pk>/', ResetPasswordView.as_view(), name='reset_password'),
            path('view_as_user/<str:instance_pk>/', ImpersonateUserView.as_view(), name='view_as_user'),
        ]


register_snippet(PersonViewSet)
