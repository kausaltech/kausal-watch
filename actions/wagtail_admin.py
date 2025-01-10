from __future__ import annotations

import re
import typing
from functools import cached_property

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import ProtectedError
from django.urls import re_path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.messages import validation_error
from wagtail.admin.panels import (
    FieldPanel,
    InlinePanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.admin.ui.tables import BulkActionsCheckboxColumn, Column
from wagtail.admin.widgets.button import ButtonWithDropdown
from wagtail.coreutils import capfirst
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import IndexView, SnippetViewSet

from dal import autocomplete
from django_filters import filters
from wagtail_modeladmin.helpers import PermissionHelper
from wagtail_modeladmin.options import modeladmin_register

from aplans.context_vars import ctx_instance, ctx_request

from actions.chooser import CategoryTypeChooser, PlanChooser
from actions.models.action import ActionSchedule
from admin_site.chooser import ClientChooser
from admin_site.menu import PlanSpecificSingletonModelMenuItem
from admin_site.mixins import SuccessUrlEditPageMixin
from admin_site.models import Client, ClientPlan
from admin_site.permissions import PlanSpecificSingletonModelSuperuserPermissionPolicy
from admin_site.viewsets import WatchEditView, WatchViewSet
from admin_site.wagtail import (
    AplansAdminModelForm,
    AplansCreateView,
    AplansEditView,
    AplansModelAdmin,
    CondensedInlinePanel,
    SuccessUrlEditPageModelAdminMixin,
    insert_model_translation_panels,
)
from copying.views import PlanCopyView
from notifications.models import NotificationSettings
from orgs.chooser import OrganizationChooser
from orgs.models import Organization
from pages.models import PlanLink
from people.chooser import PersonChooser
from users.models import User

from . import (
    action_admin,  # noqa
    attribute_type_admin,  # noqa
    category_admin,  # noqa
)
from .models import ActionImpact, ActionStatus, Plan, PlanFeatures

if typing.TYPE_CHECKING:
    from django.db.models import QuerySet
    from django.http import HttpRequest
    from wagtail.admin.menu import MenuItem


class PlanForm(AplansAdminModelForm):
    def clean_primary_language(self):
        primary_language = self.cleaned_data['primary_language']
        if self.instance and self.instance.pk and primary_language != self.instance.primary_language:
            raise ValidationError("Changing the primary language is not supported yet.")
        return primary_language

    @staticmethod
    def _clean_identifier(identifier, plan: Plan):
        qs = Plan.objects.filter(identifier=identifier)
        if plan and plan.pk:
            qs = qs.exclude(pk=plan.pk)
        if qs.count() > 0:
            raise ValidationError(_('Identifier already in use'), code='identifier-taken')
        if not re.fullmatch('[a-z]+(-[a-z]+)*(-?[0-9]+)?', identifier):
            raise ValidationError(
                _('For identifiers, use only lowercase letters from the English alphabet with dashes separating words. '
                  'Numbers are allowed only in the end.'),
            )
        return identifier

    def clean_identifier(self):
        identifier = self.cleaned_data['identifier']
        return self._clean_identifier(identifier, self.instance)

    def clean_name(self):
        name = self.cleaned_data['name']
        qs = Plan.objects.filter(name=name)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.count() > 0:
            raise ValidationError(_('Plan name already in use'), code='name-taken')
        return name

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data.get('primary_language') in cleaned_data.get('other_languages', []):
            raise ValidationError(_(
                'A plan\'s other language cannot be the same as its primary language'),
                                  code='plan-language-duplicate',
            )
        return cleaned_data

    def save(self, *args, **kwargs):
        creating = False
        if self.instance.pk is None:
            creating = True
        instance = super().save(*args, **kwargs)
        if creating:
            Plan.apply_defaults(instance)
        return instance


class PlanCreateView(AplansCreateView):
    def get_success_url(self):
        return reverse('change-admin-plan', kwargs=dict(
            plan_id=self.instance.id))


class PlanEditView(SuccessUrlEditPageModelAdminMixin, AplansEditView):
    @transaction.atomic()
    def form_valid(self, form):
        old_common_category_types = self.instance.common_category_types.all()
        new_common_category_types = form.cleaned_data['common_category_types']
        for added_cct in new_common_category_types.difference(old_common_category_types):
            # Create category type corresponding to this common category type and link it to this plan
            ct = added_cct.instantiate_for_plan(self.instance)
            # Create categories for the common categories having that common category type
            for common_category in added_cct.categories.all():
                common_category.instantiate_for_category_type(ct)
        for removed_cct in old_common_category_types.difference(new_common_category_types):
            try:
                self.instance.category_types.filter(common=removed_cct).delete()
            except ProtectedError:
                # Actually validation should have been done before this method is called, but it seems to work for now
                error = _(
                    'Could not remove common category type "%(removed_cct)" from the plan because categories '
                    'with the corresponding category type exist.',
                ) % {'removed_cct': removed_cct}
                form.add_error('common_category_types', error)
                validation_error(self.request, self.get_error_message(), form)
                return self.render_to_response(self.get_context_data(form=form))
        return super().form_valid(form)


class PlanModelAdminPermissionHelper(PermissionHelper):
    def user_can_list(self, user):
        return user.is_superuser

    def user_can_create(self, user):
        return user.is_superuser

    def user_can_inspect_obj(self, user, obj):
        return False

    def user_can_delete_obj(self, user, obj):
        return False

    def user_can_edit_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj)



class PlanAdmin(AplansModelAdmin):
    model = Plan
    add_to_admin_menu = False  # We only have PlanViewSet in the menu and use the views of PlanAdmin in that viewset
    list_display = ('name',)
    search_fields = ('name',)
    permission_helper_class = PlanModelAdminPermissionHelper
    create_view_class = PlanCreateView
    copy_view_class = PlanCopyView
    edit_view_class = PlanEditView

    panels = [
        FieldPanel('name'),
        FieldPanel('short_name'),
        FieldPanel('identifier'),
        FieldPanel('short_identifier'),
        FieldPanel('version_name'),
        FieldPanel('actions_locked'),
        FieldPanel('site_url'),
        FieldPanel('accessibility_statement_url'),
        FieldPanel('primary_language'),
        FieldPanel('other_languages'),
        FieldPanel('country'),
        FieldPanel('timezone'),
        CondensedInlinePanel(
            'general_admins_ordered',
            panels=[
                FieldPanel('person', widget=PersonChooser),
            ],
            heading=_("General administrators"),
        ),
        FieldPanel('image'),
        FieldPanel('superseded_by', widget=PlanChooser),
        FieldPanel('copy_of', widget=PlanChooser, read_only=True),
    ]

    action_impact_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
    ]

    action_schedule_panels = [
        FieldPanel('name'),
        FieldPanel('begins_at'),
        FieldPanel('ends_at'),
    ]

    COLOR_HELP_TEXT = _(
        'Only set if explicitly required by customer. Use a color key from the UI theme\'s graphColors, for example red070 or grey030.',
    )

    def copy_view(self, request, instance_pk):
        kwargs = {'plan_id': instance_pk}
        view_class = self.copy_view_class
        return view_class.as_view(**kwargs)(request)

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        urls += (
            re_path(
                self.url_helper.get_action_url_pattern('copy'),
                self.copy_view,
                name=self.url_helper.get_action_url_name('copy'),
            ),
        )
        return urls

    def get_action_status_panels(self, user: User):
        result = [
            FieldPanel('identifier'),
            FieldPanel('name'),
            FieldPanel('is_completed'),
        ]
        if user.is_superuser:
            result.append(FieldPanel('color', help_text=self.COLOR_HELP_TEXT))
        return result

    def get_action_implementation_phase_panels(self, user: User):
        result = [
            FieldPanel('identifier'),
            FieldPanel('name'),
        ]
        if user.is_superuser:
            result.append(FieldPanel('color', help_text=self.COLOR_HELP_TEXT))
        return result

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get_as_type(Plan)

        creating = instance.pk is None
        panels_enabled_when_creating = {
            'name',
            'identifier',
            'primary_language',
            'short_name',
            'other_languages',
        }

        panels = list(self.panels)

        if creating:
            # Accidentally changing a plan organization would be dangerous, so don't show this for existing plans
            create_panels = [
                FieldPanel('organization', widget=OrganizationChooser),

            ]
            panels = create_panels + [
                p for p in panels
                if getattr(p, 'field_name', None) in panels_enabled_when_creating
            ]

        action_status_panels = insert_model_translation_panels(
            ActionStatus, self.get_action_status_panels(request.user), request, instance,
        )
        action_implementation_phase_panels = insert_model_translation_panels(
            ActionStatus, self.get_action_implementation_phase_panels(request.user), request, instance,
        )
        action_impact_panels = insert_model_translation_panels(
            ActionImpact, self.action_impact_panels, request, instance,
        )
        action_schedule_panels = insert_model_translation_panels(
            ActionSchedule, self.action_schedule_panels, request, instance,
        )

        panels = list(insert_model_translation_panels(
            Plan, panels, request, instance,
        ))
        if request.user.is_superuser:
            panels.append(InlinePanel('clients', min_num=1, panels=[
                FieldPanel('client', widget=ClientChooser),
                ], heading=_('Clients')))
            panels.append(FieldPanel('usage_status'))
            panels.append(FieldPanel('kausal_paths_instance_uuid'))
        if not creating and request.user.is_superuser:
            panels.append(FieldPanel('theme_identifier'))
            panels.append(InlinePanel('domains', panels=[
                FieldPanel('hostname'),
                FieldPanel('base_path'),
                FieldPanel('deployment_environment'),
                FieldPanel('redirect_aliases'),
                FieldPanel('google_site_verification_tag'),
                FieldPanel('matomo_analytics_url'),
            ], heading=_('Domains')))

        links_panel = CondensedInlinePanel[Plan, PlanLink](
            'links',
            panels=(
                FieldPanel('url'),
                FieldPanel('title'),
            ),
            heading=_('External links'),
        )
        links_panel.panels = insert_model_translation_panels(PlanLink, links_panel.panels, request, instance)
        if not creating:
            panels.append(links_panel)
            panels.append(FieldPanel('external_feedback_url'))

        tabs = [ObjectList(panels, heading=_('Basic information'))]
        if not creating:
            tabs.append(
                ObjectList([
                    FieldPanel('primary_action_classification', widget=CategoryTypeChooser),
                    CondensedInlinePanel('action_statuses', panels=action_status_panels, heading=_('Action statuses')),
                    CondensedInlinePanel(
                        'action_implementation_phases',
                        panels=action_implementation_phase_panels,
                        heading=_('Action implementation phases'),
                    ),
                    CondensedInlinePanel('action_impacts', panels=action_impact_panels, heading=_('Action impacts')),
                    CondensedInlinePanel('action_schedules', panels=action_schedule_panels, heading=_('Action schedules')),
                    FieldPanel(
                        'common_category_types',
                        widget=autocomplete.ModelSelect2Multiple(url='commoncategorytype-autocomplete'),
                    ),
                    FieldPanel('secondary_action_classification', widget=CategoryTypeChooser),
                    FieldPanel('settings_action_update_target_interval'),
                    FieldPanel('settings_action_update_acceptable_interval'),
                    FieldPanel('action_days_until_considered_stale'),
                    CondensedInlinePanel(
                        'action_dependency_roles',
                        panels=[
                            FieldPanel('name'),
                        ],
                        heading=_("Action dependency roles"),
                    ),
                ], heading=_('Action classifications')),
            )

        handler = TabbedInterface(tabs, base_form_class=PlanForm)
        return handler

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(general_admins=person).distinct()
        return qs


modeladmin_register(PlanAdmin)


class PlanFeaturesViewSet(WatchViewSet):
    model = PlanFeatures
    icon = 'tasks'
    menu_label = _('Plan features')
    menu_order = 501

    panels = [
        FieldPanel('enable_search'),
        FieldPanel('enable_indicator_comparison'),
        FieldPanel('indicator_ordering'),
        # Arbitrary string as the 'permission' parameter, here 'superuser', can
        # be used as a way to restrict a panel only to superusers. This is the
        # recommended approach given in Wagtail docs as of writing:
        # https://docs.wagtail.org/en/v6.1.3/reference/pages/panels.html#wagtail.admin.panels.FieldPanel.permission
        FieldPanel('allow_images_for_actions', permission='superuser'),
        FieldPanel('show_admin_link', permission='superuser'),
        FieldPanel('allow_public_site_login', permission='superuser'),
        FieldPanel('contact_persons_public_data', permission='superuser'),
        FieldPanel('contact_persons_show_picture', permission='superuser'),
        FieldPanel('contact_persons_show_organization_ancestors', permission='superuser'),
        FieldPanel('contact_persons_hide_moderators', permission='superuser'),
        FieldPanel('has_action_identifiers', permission='superuser'),
        FieldPanel('show_action_identifiers', permission='superuser'),
        FieldPanel('has_action_official_name', permission='superuser'),
        FieldPanel('has_action_lead_paragraph', permission='superuser'),
        FieldPanel('has_action_primary_orgs', permission='superuser'),
        FieldPanel('has_action_contact_person_roles', permission='superuser'),
        FieldPanel('minimal_statuses', permission='superuser'),
        FieldPanel('moderation_workflow', permission='superuser'),
        FieldPanel('display_field_visibility_restrictions', permission='superuser'),
        FieldPanel('output_report_action_print_layout', permission='superuser'),
        FieldPanel('password_protected', permission='superuser'),
    ]

    def get_queryset(self, request):
        qs = self.model.objects.get_queryset()
        user = request.user
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(plan__general_admins=person).distinct()
        return qs


# TBD: We might want to keep this for superusers.
# register_snippet(PlanFeaturesViewSet)


class ActivePlanFeaturesMenuItem(PlanSpecificSingletonModelMenuItem):
    def get_one_to_one_field(self, plan):
        return plan.features


class ActivePlanFeaturesEditView(SuccessUrlEditPageMixin, WatchEditView):
    def user_has_permission(self, permission):
        return self.permission_policy.user_has_permission_for_instance(self.request.user, permission, self.object)


class ActivePlanFeaturesViewSet(PlanFeaturesViewSet):
    edit_view_class = ActivePlanFeaturesEditView
    add_to_settings_menu = True

    def get_menu_item(self, order=None):
        return ActivePlanFeaturesMenuItem(self, order or self.menu_order)

    @property
    def permission_policy(self):
        # TODO: Commit history looks like this viewset was meant to be open for
        # plan admins, but due to a bug was really open only for superusers.
        # Restrict access to superusers to keep the functionality same for now.
        # Check in the future if this viewset should be opened up for plan
        # admins.
        return PlanSpecificSingletonModelSuperuserPermissionPolicy(self.model)


register_snippet(ActivePlanFeaturesViewSet)


class NotificationSettingsViewSet(WatchViewSet):
    model = NotificationSettings
    icon = 'fontawesome-bell'
    menu_label = _('Plan notification settings')
    menu_order = 502

    panels = [
        FieldPanel('notifications_enabled'),
        FieldPanel('send_at_time'),
    ]

    def get_queryset(self, request):
        qs = self.model.objects.get_queryset()
        user = request.user
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(plan__general_admins=person).distinct()
        return qs


class ActivePlanNotificationSettingsMenuItem(PlanSpecificSingletonModelMenuItem):
    def get_one_to_one_field(self, plan):
        return plan.notification_settings


class ActivePlanNotificationSettingsEditView(SuccessUrlEditPageMixin, WatchEditView):
    pass


class ActivePlanNotificationSettingsViewSet(NotificationSettingsViewSet):
    edit_view_class = ActivePlanNotificationSettingsEditView
    menu_label = _('Plan notification settings')
    add_to_settings_menu = True

    @property
    def permission_policy(self):
        # TODO: Commit history looks like this viewset was meant to be open for
        # plan admins, but due to a bug was really open only for superusers.
        # Restrict access to superusers to keep the functionality same for now.
        # Check in the future if this viewset should be opened up for plan
        # admins.
        return PlanSpecificSingletonModelSuperuserPermissionPolicy(self.model)

    def get_menu_item(self, order=None):
        item = ActivePlanNotificationSettingsMenuItem(self, order or self.menu_order)
        return item


register_snippet(ActivePlanNotificationSettingsViewSet)


class PlanIndexView(IndexView[Plan]):
    # FIXME: in yet unreleased Wagtail 6.2.X this is the default, so this line can be deleted
    any_permission_required = ["add", "change", "delete", "view"]
    permission_required = 'view'
    additional_fields_cache: list[str] | None = None

    def _get_additional_fields(self) -> list[str]:
        """Get a list of all user-defined additional fields of the feedback form present in the queryset."""
        if self.additional_fields_cache is not None:
            return self.additional_fields_cache

        additional_fields = []
        for feedback in self.get_queryset():
            if feedback.additional_fields is not None:
                additional_fields += feedback.additional_fields.keys()

        duplicates_removed = list(dict.fromkeys(additional_fields))
        self.additional_fields_cache = duplicates_removed
        return self.additional_fields_cache

    def get_list_buttons(self, instance: Plan):
        buttons = super().get_list_buttons(instance)
        # This will now contain a ButtonWithDropdown. Wagtail doesn't expect that this button has no "subbuttons", but
        # this can happen in our case for users with little permissions (e.g., contact persons). So we discard those
        # ButtonWithDropdown instances that don't have any dropdown buttons.
        buttons = [b for b in buttons if not (isinstance(b, ButtonWithDropdown) and not b.dropdown_buttons)]
        return buttons

    def _get_title_column(self, *args, **kwargs) -> Column:
        # Make the link in the title column change the active admin plan instead of editing the plan.
        column = super()._get_title_column(*args, **kwargs)

        def change_plan_url(plan: Plan) -> str:
            return reverse('change-admin-plan', kwargs={'plan_id': plan.id})

        column._get_url_func = change_plan_url  # pyright: ignore[reportAttributeAccessIssue]
        return column

    @cached_property
    def columns(self):  # pyright: ignore[reportIncompatibleVariableOverride]
        return [c for c in super().columns if not isinstance(c, BulkActionsCheckboxColumn)]


def clients_for_request(request: HttpRequest):
    if request is None or request.user.is_anonymous:
        return Client.objects.none()
    assert isinstance(request.user, User)
    plans = request.user.get_adminable_plans()
    clients = Client.objects.filter(id__in=ClientPlan.objects.filter(plan_id__in=plans).values_list('client_id'))
    return clients.order_by('name')


class PlanFilter(WagtailFilterSet):
    clients__client = filters.ModelChoiceFilter(
        queryset=clients_for_request,
        label=capfirst(Client._meta.verbose_name),
    )

    class Meta:
        model = Plan
        fields = ['clients__client']


class PlanViewSet(SnippetViewSet[Plan]):
    model = Plan
    add_to_admin_menu = True
    icon = 'kausal-plan'
    menu_label = _('Plans')
    menu_order = 9000
    list_display = ['name', 'version_name', 'parent', 'organization', 'clients_as_string']
    filterset_class = PlanFilter
    list_per_page = None  # disable pagination
    index_view_class = PlanIndexView
    # Note that we can't use PlanCopyView as copy_view_class because it is not a (snippet) CopyView

    # Copied from UserFeedbackViewSet
    # FIXME: As of writing this latest Wagtail (6.1.X) has a bug which only
    # shows the menu item when user has "add", "change" or "delete" permission,
    # while "view" should be enough. (See
    # https://github.com/wagtail/wagtail/blob/747d70e0656b86e3e8c8d123ecae82fa61cd1438/wagtail/admin/viewsets/model.py#L521C16-L521C58
    # for the specific line of code). This seems to be fixed in the latest
    # still unreleased Wagtail code, so when upgraded to Wagtail 6.2.X this
    # workaround should be safe to delete.
    def get_menu_item(self, order: int | None = None) -> MenuItem:
        menu_item = super().get_menu_item(order)
        menu_item.is_shown = lambda request: True  # type: ignore[method-assign] # noqa: ARG005
        return menu_item

    def get_url_name(self, view_name: str) -> str:
        # We use a terrifying mix of modeladmin and snippet views. Once we got rid of modeladmin, change this.
        if view_name == 'add':
            return 'actions_plan_modeladmin_create'
        if view_name == 'copy':
            return 'actions_plan_modeladmin_copy'
        if view_name == 'edit':
            return 'actions_plan_modeladmin_edit'
        return super().get_url_name(view_name)

    def get_queryset(self, request: HttpRequest) -> QuerySet | None:
        if request.user.is_anonymous:
            return Plan.objects.none()
        assert isinstance(request.user, User)
        return request.user.get_adminable_plans()


register_snippet(PlanViewSet)


# Monkeypatch Organization to support Wagtail autocomplete
def org_autocomplete_label(self):
    return self.distinct_name


Organization.autocomplete_search_field = 'distinct_name'
Organization.autocomplete_label = org_autocomplete_label
