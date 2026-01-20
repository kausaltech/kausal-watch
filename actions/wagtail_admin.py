from __future__ import annotations

import re
from functools import cached_property
from typing import TYPE_CHECKING, Any, ClassVar, override

from django.contrib.admin.utils import quote
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, transaction
from django.db.models import ProtectedError
from django.shortcuts import redirect
from django.urls import path, re_path, reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from django.views.generic import TemplateView
from wagtail.admin import messages
from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.messages import validation_error
from wagtail.admin.panels import (
    FieldPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
    TabbedInterface,
)
from wagtail.admin.ui.tables import BulkActionsCheckboxColumn, Column
from wagtail.admin.views.generic.base import (
    BaseObjectMixin,
    WagtailAdminTemplateMixin,
)
from wagtail.admin.views.generic.permissions import PermissionCheckedMixin
from wagtail.admin.widgets.button import ButtonWithDropdown
from wagtail.coreutils import capfirst
from wagtail.log_actions import log
from wagtail.snippets import widgets as wagtailsnippets_widgets
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import DeleteView as SnippetDeleteView, IndexView, SnippetViewSet

from dal import autocomplete
from django_filters import filters
from wagtail_color_panel.edit_handlers import NativeColorPanel
from wagtail_modeladmin.helpers.permission import PermissionHelper
from wagtail_modeladmin.options import ModelAdminMenuItem, modeladmin_register

from kausal_common.people.chooser import PersonChooser
from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request

from actions.chooser import CategoryTypeChooser, PlanChooser
from actions.models.action import ActionSchedule, BaseChangeLogMessage
from admin_site.chooser import ClientChooser
from admin_site.menu import PlanSpecificSingletonModelMenuItem
from admin_site.mixins import SuccessUrlEditPageMixin
from admin_site.models import Client, ClientPlan
from admin_site.permissions import (
    PlanSpecificSingletonModelPermissionPolicy,
    PlanSpecificSingletonModelSuperuserPermissionPolicy,
)
from admin_site.viewsets import (
    BaseChangeLogMessageCreateView,
    BaseChangeLogMessageDeleteView,
    BaseChangeLogMessageEditView,
    BaseChangeLogMessageViewSet,
    WatchEditView,
    WatchViewSet,
)
from admin_site.wagtail import (
    ActivePlanEditView,
    AplansAdminModelForm,
    AplansCreateView,
    AplansEditView,
    AplansModelAdmin,
    CondensedInlinePanel,
    SuccessUrlEditPageModelAdminMixin,
    insert_model_translation_panels,
)
from copying.views import PlanCopyView
from indicators.models import Indicator
from notifications.models import NotificationSettings
from orgs.chooser import OrganizationChooser
from orgs.models import Organization
from pages.models import PlanLink
from users.models import User

from . import (
    action_admin,  # noqa: F401
    attribute_type_admin,  # noqa: F401
    category_admin,  # noqa: F401
)
from .models import (
    Action,
    ActionChangeLogMessage,
    ActionImpact,
    ActionStatus,
    Category,
    CategoryChangeLogMessage,
    IndicatorChangeLogMessage,
    Plan,
    PlanFeatures,
)

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.admin.menu import MenuItem
    from wagtail.admin.panels.base import Panel

    from aplans.types import WatchAdminRequest

    from actions.models.plan import PlanQuerySet


class PlanForm(AplansAdminModelForm[Plan]):
    def clean_primary_language(self):
        primary_language = self.cleaned_data['primary_language']
        if self.instance and self.instance.pk and primary_language != self.instance.primary_language:
            raise ValidationError('Changing the primary language is not supported yet.')
        return primary_language

    @staticmethod
    def _clean_identifier(identifier: str, plan: Plan) -> str:
        qs = Plan.objects.filter(identifier=identifier)
        if plan and plan.pk:
            qs = qs.exclude(pk=plan.pk)
        if qs.count() > 0:
            raise ValidationError(_('Identifier already in use'), code='identifier-taken')
        if not re.fullmatch('[a-z]+(-[a-z]+)*(-?[0-9]+)?', identifier):
            raise ValidationError(
                _(
                    'For identifiers, use only lowercase letters from the English alphabet with dashes separating words. '
                    'Numbers are allowed only in the end.'
                ),
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
        assert cleaned_data is not None
        if cleaned_data.get('primary_language') in cleaned_data.get('other_languages', []):
            raise ValidationError(
                _("A plan's other language cannot be the same as its primary language"),
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


class PlanCreateView(AplansCreateView[Plan]):
    def get_success_url(self):
        return reverse('change-admin-plan', kwargs=dict(plan_id=self.instance.id))


class PlanEditView(SuccessUrlEditPageModelAdminMixin, AplansEditView[Plan]):
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


class PlanAdmin(AplansModelAdmin[Plan]):
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
            heading=_('General administrators'),
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
        "Only set if explicitly required by customer. Use a color key from the UI theme's graphColors, for example red070 "
        "or grey030.",
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
            # We deliberately don't use NativeColorPanel from wagtail_color_panel here because here we expect color keys
            # from the UI theme's graphColors, such as "red030", instead of hex colors.
            result.append(NativeColorPanel('color', help_text=self.COLOR_HELP_TEXT))
        return result

    def get_action_implementation_phase_panels(self, user: User):
        result = [
            FieldPanel('identifier'),
            FieldPanel('name'),
        ]
        if user.is_superuser:
            # We deliberately don't use NativeColorPanel from wagtail_color_panel here because here we expect color keys
            # from the UI theme's graphColors, such as "red030", instead of hex colors.
            result.append(NativeColorPanel('color', help_text=self.COLOR_HELP_TEXT))
        return result

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get_as_type(Plan)

        creating = instance.pk is None
        panels_enabled_when_creating = {
            'name',
            'identifier',
            'short_name',
            'primary_language',
            'other_languages',
            'country',
        }

        panels: list[Panel[Any, Any]] = list(self.panels)

        if creating:
            # Accidentally changing a plan organization would be dangerous, so don't show this for existing plans
            create_panels = [
                FieldPanel('organization', widget=OrganizationChooser),
            ]
            panels = create_panels + [p for p in panels if getattr(p, 'field_name', None) in panels_enabled_when_creating]

        user = user_or_bust(request.user)
        action_status_panels = insert_model_translation_panels(
            ActionStatus,
            self.get_action_status_panels(user),
            request,
            instance,
        )
        action_implementation_phase_panels = insert_model_translation_panels(
            ActionStatus,
            self.get_action_implementation_phase_panels(user),
            request,
            instance,
        )
        action_impact_panels = insert_model_translation_panels(
            ActionImpact,
            self.action_impact_panels,
            request,
            instance,
        )
        action_schedule_panels = insert_model_translation_panels(
            ActionSchedule,
            self.action_schedule_panels,
            request,
            instance,
        )

        panels = list(
            insert_model_translation_panels(
                Plan,
                panels,
                request,
                instance,
            )
        )
        if user.is_superuser:
            panels.append(
                InlinePanel(
                    'clients',
                    min_num=1,
                    panels=[
                        FieldPanel('client', widget=ClientChooser),
                    ],
                    heading=_('Clients'),
                )
            )
            panels.append(FieldPanel('usage_status'))
            panels.append(FieldPanel('kausal_paths_instance_uuid'))
        if not creating and user.is_superuser:
            panels.append(FieldPanel('theme_identifier'))
            panels.append(InlinePanel('domains', panels=[
                FieldPanel('hostname'),
                FieldPanel('base_path'),
                FieldPanel('redirect_to_hostname'),
                FieldPanel('deployment_environment'),
                FieldPanel('redirect_aliases'),
                FieldPanel('google_site_verification_tag'),
                FieldPanel('matomo_analytics_url'),
            ], heading=_('Domains')))

        links_panel = CondensedInlinePanel[Plan, PlanLink](  # type: ignore[assignment]
            'links',
            panels=(
                FieldPanel('url'),
                FieldPanel('title'),
            ),
            heading=_('External links'),
        )
        assert links_panel.panels is not None
        links_panel.panels = insert_model_translation_panels(PlanLink, links_panel.panels, request, instance)
        if not creating:
            panels.append(links_panel)
            panels.append(FieldPanel('external_feedback_url'))

        tabs = [ObjectList(panels, heading=_('Basic information'))]
        if not creating:
            tabs.append(
                ObjectList(
                    [
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
                            heading=_('Action dependency roles'),
                        ),
                    ],
                    heading=_('Action classifications'),
                ),
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


class PlanFeaturesViewSet(WatchViewSet[PlanFeatures]):
    model = PlanFeatures
    icon = 'tasks'
    menu_label = _('Plan features')
    menu_order = 501

    plan_admin_panels = [
        FieldPanel('enable_search'),
        FieldPanel('enable_indicator_comparison'),
        FieldPanel('indicator_ordering'),
        FieldPanel('indicators_open_in_modal'),
        FieldPanel('enable_change_log'),
    ]

    # Arbitrary string as the 'permission' parameter, here 'superuser', can
    # be used as a way to restrict a panel only to superusers. This is the
    # recommended approach given in Wagtail docs as of writing:
    # https://docs.wagtail.org/en/v6.1.3/reference/pages/panels.html#wagtail.admin.panels.FieldPanel.permission
    superuser_only_panels = [
        FieldPanel('allow_images_for_actions', permission='superuser'),
        FieldPanel('show_admin_link', permission='superuser'),
        FieldPanel('allow_public_site_login', permission='superuser'),
        FieldPanel('expose_unpublished_plan_only_to_authenticated_user', permission='superuser'),
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

    # Define all panels explicitly to prevent Wagtail from auto-generating form fields
    # for all model attributes. This list is overridden by ActivePlanFeaturesEditView.get_panel()
    # which dynamically constructs panels based on user permissions using the plan_admin_panels
    # and superuser_only_panels defined above.
    panels = plan_admin_panels + superuser_only_panels

    def get_queryset(self, request):
        qs = self.model.objects.get_queryset()
        user = user_or_bust(request.user)
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(plan__general_admins=person).distinct()
        return qs


# TBD: We might want to keep this for superusers.
# register_snippet(PlanFeaturesViewSet)


class ActivePlanFeaturesMenuItem(PlanSpecificSingletonModelMenuItem):
    def get_one_to_one_field(self, plan):
        return plan.features


class ActivePlanFeaturesEditView(SuccessUrlEditPageMixin, WatchEditView[PlanFeatures]):
    def user_has_permission(self, permission):
        return self.permission_policy.user_has_permission_for_instance(self.request.user, permission, self.object)

    def get_panel(self):
        user = user_or_bust(self.request.user)

        if user.is_superuser:
            # Show grouped panels for superusers
            panels: list = [
                MultiFieldPanel(
                    PlanFeaturesViewSet.plan_admin_panels,
                    heading=_('Plan features that plan admins are allowed to change'),
                ),
                MultiFieldPanel(
                    PlanFeaturesViewSet.superuser_only_panels,
                    heading=_('Plan features that only superusers are allowed to change'),
                    permission='superuser',
                ),
            ]
        else:
            # Show only plan admin fields without grouping for non-superusers
            panels = PlanFeaturesViewSet.plan_admin_panels

        return ObjectList(panels).bind_to_model(self.model)


class ActivePlanFeaturesViewSet(PlanFeaturesViewSet):
    edit_view_class = ActivePlanFeaturesEditView
    add_to_settings_menu = True

    def get_menu_item(self, order=None):
        return ActivePlanFeaturesMenuItem(self, order or self.menu_order)

    @property
    def permission_policy(self):
        return PlanSpecificSingletonModelPermissionPolicy(self.model)


register_snippet(ActivePlanFeaturesViewSet)


class NotificationSettingsViewSet(WatchViewSet[NotificationSettings]):
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
        user = user_or_bust(request.user)
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(plan__general_admins=person).distinct()
        return qs


class ActivePlanNotificationSettingsMenuItem(PlanSpecificSingletonModelMenuItem):
    def get_one_to_one_field(self, plan):
        return plan.notification_settings


class ActivePlanNotificationSettingsEditView(SuccessUrlEditPageMixin, WatchEditView[NotificationSettings]):
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


class PublicationStatusColumn(Column):
    cell_template_name = "aplans/plan_publication_status_cell.html"

    def __init__(self, name: str = 'publication_status', **kwargs):
        super().__init__(name, label=_('Publication status'), **kwargs)

    def get_cell_context_data(self, instance: Plan, parent_context):
        context = super().get_cell_context_data(instance, parent_context)
        state = instance.publication_state
        tooltip = instance.publication_status_description

        status_class_map = {
            Plan.PublicationState.INTERNAL: 'w-status--internal',
            Plan.PublicationState.PUBLIC: 'w-status--public',
            Plan.PublicationState.SCHEDULED: 'w-status--scheduled',
        }
        context['status_class'] = status_class_map[state]
        context['status_label'] = state.label

        context['tooltip'] = tooltip
        return context


class PlanIndexView(IndexView[Plan]):
    # FIXME: in yet unreleased Wagtail 6.2.X this is the default, so this line can be deleted
    any_permission_required = ['add', 'change', 'delete', 'view']
    permission_required = 'view'
    publish_url_name: str | None = None
    unpublish_url_name: str | None = None
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
    def columns(self):  # type: ignore[override]
        return [c for c in super().columns if not isinstance(c, BulkActionsCheckboxColumn)]

    def get_publish_url(self, instance: Plan) -> str:
        return reverse(self.publish_url_name, kwargs={'pk': quote(instance.pk)})

    def get_unpublish_url(self, instance: Plan) -> str:
        return reverse(self.unpublish_url_name, kwargs={'pk': quote(instance.pk)})

    def publish_button(self, instance: Plan):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_publish_url(instance),
            label=_('Publish'),
            icon_name='upload',
            attrs={'aria-label': _('Publish this plan')},
        )

    def unpublish_button(self, instance: Plan):
        return wagtailsnippets_widgets.SnippetListingButton(
            url=self.get_unpublish_url(instance),
            label=_('Unpublish'),
            icon_name='download',
            attrs={'aria-label': _('Unpublish this plan')},
        )

    def get_list_more_buttons(self, instance: Plan):
        buttons = list(super().get_list_more_buttons(instance))
        user = user_or_bust(self.request.user)
        # TODO: Enable for general admins once ready for customer use
        # if not user.is_general_admin_for_plan(instance):
        #     return buttons
        if not user.is_superuser:
            return buttons

        if instance.is_live():
            buttons.append(self.unpublish_button(instance))
        else:
            buttons.append(self.publish_button(instance))

        return buttons


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


class PlanPublishView(
    BaseObjectMixin[Plan],
    PermissionCheckedMixin,
    WagtailAdminTemplateMixin,
    TemplateView,
):
    model = Plan
    permission_required = 'publish'
    publish = True
    template_name = 'aplans/plan_publish_confirmation.html'
    index_url_name: ClassVar[str | None] = None

    def user_has_permission(self, permission: str) -> bool:
        user = user_or_bust(self.request.user)
        # TODO: Enable for general admins once ready for customer use
        # return user.is_general_admin_for_plan(self.object)
        return user.is_superuser

    def get_page_title(self):
        if self.publish:
            return _("Publish plan")
        return _("Unpublish plan")

    def get_meta_title(self):
        if self.publish:
            msg = _("Confirm publishing %(plan)s")
        else:
            msg = _("Confirm unpublishing %(plan)s")
        return msg % {'plan': self.object}

    def confirmation_message(self):
        if self.publish:
            return _("Do you want to publish the plan '%(plan)s'? This will make it publicly accessible.") % {
                'plan': self.object
            }
        return _(
            "Do you want to unpublish the plan '%(plan)s'? "
            "This will make it inaccessible to the public."
        ) % {'plan': self.object}

    def do_publish(self):
        if self.object.is_live():
            raise ValueError(_("The plan is already published."))
        self.object.published_at = timezone.now()
        self.object.save(update_fields=['published_at'])
        self.object.invalidate_cache()
        log(
            instance=self.object,
            action='plan.publish',
            user=self.request.user,
        )

    def do_unpublish(self):
        if not self.object.is_live():
            raise ValueError(_("The plan is already unpublished."))
        self.object.published_at = None
        self.object.save(update_fields=['published_at'])
        self.object.invalidate_cache()
        log(
            instance=self.object,
            action='plan.unpublish',
            user=self.request.user,
        )

    def get_production_urls(self):
        from actions.models.plan import PlanDomain
        domains = self.object.domains.filter(
            deployment_environment=PlanDomain.DeploymentEnvironment.PRODUCTION
        )
        return [f"https://{domain.hostname}" for domain in domains]

    def get_preview_url(self):
        try:
            return f"https://{self.object.default_hostname()}"
        except Exception:
            return None

    def is_scheduled(self):
        return self.object.publication_state == Plan.PublicationState.SCHEDULED

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['production_urls'] = self.get_production_urls()
        context['preview_url'] = self.get_preview_url()
        context['is_scheduled'] = self.is_scheduled()
        context['scheduled_info'] = self.object.publication_status_description if self.is_scheduled() else None
        return context

    def post(self, request, *args, **kwargs):
        try:
            if self.publish:
                self.do_publish()
            else:
                self.do_unpublish()
        except ValueError as e:
            messages.error(request, str(e))
            return redirect(self.index_url)
        if self.publish:
            msg = _("Plan '%(plan)s' has been published.")
        else:
            msg = _("Plan '%(plan)s' has been unpublished.")
        messages.success(request, msg % {'plan': self.object})
        return redirect(self.index_url)

    @cached_property
    def index_url(self):
        return reverse(self.index_url_name)


class PlanViewSet(SnippetViewSet[Plan]):
    model = Plan
    add_to_admin_menu = True
    icon = 'kausal-plan'
    menu_label = _('Plans')
    menu_order = 9000
    list_display = [
        'name', 'version_name', 'parent', 'organization', 'clients_as_string',
        PublicationStatusColumn(),
    ]
    filterset_class = PlanFilter
    list_per_page = None  # disable pagination
    index_view_class = PlanIndexView
    publish_url_name = 'publish'
    unpublish_url_name = 'unpublish'
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

    def get_queryset(self, request: HttpRequest) -> PlanQuerySet | None:
        if request.user.is_anonymous:
            return Plan.objects.qs.none()
        assert isinstance(request.user, User)
        return request.user.get_adminable_plans()

    @property
    def publish_view(self):
        return self.construct_view(PlanPublishView, publish=True)

    @property
    def unpublish_view(self):
        return self.construct_view(PlanPublishView, publish=False)

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(
            publish_url_name=self.get_url_name(self.publish_url_name),
            unpublish_url_name=self.get_url_name(self.unpublish_url_name),
            **kwargs,
        )

    def get_urlpatterns(self):
        urls = super().get_urlpatterns()
        publish_url = path(
            f'{self.publish_url_name}/<str:pk>/',
            view=self.publish_view,
            name=self.publish_url_name,
        )
        unpublish_url = path(
            f'{self.unpublish_url_name}/<str:pk>/',
            view=self.unpublish_view,
            name=self.unpublish_url_name,
        )
        return [*urls, publish_url, unpublish_url]


register_snippet(PlanViewSet)


class ActionChangeLogMessageCreateView(BaseChangeLogMessageCreateView[ActionChangeLogMessage, Action]):
    related_field_name = 'action'
    success_url_name = 'actions_action_modeladmin_index'

    @override
    def get_related_object_by_pk(self, pk: str) -> Action | None:
        try:
            return Action.objects.get(pk=pk)
        except Action.DoesNotExist:
            return None

    def get_revision_id(self) -> str | None:
        """Get revision ID from GET params or POST data (hidden field)."""
        if self.request.method == 'POST':
            return self.request.POST.get('revision')
        return self.request.GET.get('revision')

    def get_form(self, *args, **kwargs):
        form = super().get_form(*args, **kwargs)
        revision_id = self.get_revision_id()
        if revision_id:
            from wagtail.models import Revision
            revision = Revision.objects.filter(pk=revision_id).first()
            if revision:
                form.instance.revision = revision
        return form

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['revision_id'] = self.get_revision_id()
        return context

    def check_related_object_permission(self, related_obj: Action | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_action(action=related_obj)


class ActionChangeLogMessageEditView(BaseChangeLogMessageEditView[ActionChangeLogMessage, Action]):
    related_field_name = 'action'
    success_url_name = 'actions_action_modeladmin_edit'

    def check_related_object_permission(self, related_obj: Action | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_action(action=related_obj)


class ActionChangeLogMessageDeleteView(BaseChangeLogMessageDeleteView[ActionChangeLogMessage, Action]):
    related_field_name = 'action'

    def check_related_object_permission(self, related_obj: Action | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_action(action=related_obj)


class ActionChangeLogMessageViewSet(BaseChangeLogMessageViewSet[ActionChangeLogMessage]):
    model = ActionChangeLogMessage
    menu_label = pgettext_lazy('menu label', 'Action change history messages')
    plan_filter_path = 'plan'
    add_view_class = ActionChangeLogMessageCreateView
    edit_view_class = ActionChangeLogMessageEditView
    delete_view_class = ActionChangeLogMessageDeleteView


register_snippet(ActionChangeLogMessageViewSet)


class IndicatorChangeLogMessageCreateView(BaseChangeLogMessageCreateView[IndicatorChangeLogMessage, Indicator]):
    related_field_name = 'indicator'
    success_url_name = 'indicators_indicator_modeladmin_index'

    def get_related_object_by_pk(self, pk: str) -> Indicator | None:
        try:
            return Indicator.objects.get(pk=pk)
        except Indicator.DoesNotExist:
            return None

    def check_related_object_permission(self, related_obj: Indicator | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_indicator(indicator=related_obj)


class IndicatorChangeLogMessageEditView(BaseChangeLogMessageEditView[IndicatorChangeLogMessage, Indicator]):
    related_field_name = 'indicator'
    success_url_name = 'indicators_indicator_modeladmin_edit'

    def check_related_object_permission(self, related_obj: Indicator | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_indicator(indicator=related_obj)


class IndicatorChangeLogMessageDeleteView(BaseChangeLogMessageDeleteView[IndicatorChangeLogMessage, Indicator]):
    related_field_name = 'indicator'

    def check_related_object_permission(self, related_obj: Indicator | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_indicator(indicator=related_obj)


class IndicatorChangeLogMessageViewSet(BaseChangeLogMessageViewSet[IndicatorChangeLogMessage]):
    model = IndicatorChangeLogMessage
    menu_label = pgettext_lazy('menu label', 'Indicator change history messages')
    plan_filter_path = 'plan'
    add_view_class = IndicatorChangeLogMessageCreateView
    edit_view_class = IndicatorChangeLogMessageEditView
    delete_view_class = IndicatorChangeLogMessageDeleteView


register_snippet(IndicatorChangeLogMessageViewSet)


class CategoryChangeLogMessageCreateView(BaseChangeLogMessageCreateView[CategoryChangeLogMessage, Category]):
    related_field_name = 'category'
    success_url_name = 'actions_category_modeladmin_index'

    def get_related_object_by_pk(self, pk: str) -> Category | None:
        try:
            return Category.objects.get(pk=pk)
        except Category.DoesNotExist:
            return None

    def check_related_object_permission(self, related_obj: Category | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_category(category=related_obj)


class CategoryChangeLogMessageEditView(BaseChangeLogMessageEditView[CategoryChangeLogMessage, Category]):
    related_field_name = 'category'
    success_url_name = 'actions_category_modeladmin_edit'

    def check_related_object_permission(self, related_obj: Category | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_category(category=related_obj)


class CategoryChangeLogMessageDeleteView(BaseChangeLogMessageDeleteView[CategoryChangeLogMessage, Category]):
    related_field_name = 'category'

    def check_related_object_permission(self, related_obj: Category | None) -> bool:
        if related_obj is None:
            return False
        return user_or_bust(self.request.user).can_modify_category(category=related_obj)


class CategoryChangeLogMessageViewSet(BaseChangeLogMessageViewSet[CategoryChangeLogMessage]):
    model = CategoryChangeLogMessage
    menu_label = pgettext_lazy('menu label', 'Category change history messages')
    plan_filter_path = 'plan'
    add_view_class = CategoryChangeLogMessageCreateView
    edit_view_class = CategoryChangeLogMessageEditView
    delete_view_class = CategoryChangeLogMessageDeleteView


register_snippet(CategoryChangeLogMessageViewSet)


# Monkeypatch Organization to support Wagtail autocomplete
def org_autocomplete_label(self):
    return self.distinct_name


Organization.autocomplete_search_field = 'distinct_name'  # type: ignore[attr-defined]
Organization.autocomplete_label = org_autocomplete_label  # type: ignore[attr-defined]


# FIXME: This is partly duplicated in content/admin.py.
class ActivePlanModelAdminPermissionHelper(PermissionHelper):
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


# TODO: Reimplemented in admin_site/menu.py to make this work without
# ModelAdmin. Use that when implementing new classes or migrating away from
# ModelAdmin. Remove this class when ModelAdmin migration is finished.
class PlanSpecificSingletonModelAdminMenuItem(ModelAdminMenuItem):
    def get_one_to_one_field(self, _plan):
        # Implement in subclass
        raise NotImplementedError()

    def render_component(self, request):
        # When clicking the menu item, use the edit view instead of the index view.
        link_menu_item = super().render_component(request)
        plan = user_or_bust(request.user).get_active_admin_plan()
        field = self.get_one_to_one_field(plan)
        link_menu_item.url = self.model_admin.url_helper.get_action_url('edit', field.pk)  # type: ignore[attr-defined]
        return link_menu_item

    def is_shown(self, request: WatchAdminRequest):
        # The overridden superclass method returns True iff user_can_list from the permission helper returns true. But
        # this menu item is about editing a plan features instance, not listing.
        user = request.user
        if user.is_superuser:
            return True
        plan = request.user.get_active_admin_plan(required=False)
        if plan is None:
            return False
        field = self.get_one_to_one_field(plan)
        return self.model_admin.permission_helper.user_can_edit_obj(request.user, field)


class ActivePlanMenuItem(PlanSpecificSingletonModelAdminMenuItem):
    def get_one_to_one_field(self, plan):
        return plan


class ActivePlanAdmin(PlanAdmin):
    edit_view_class = ActivePlanEditView
    permission_helper_class = ActivePlanModelAdminPermissionHelper  # type: ignore[assignment]
    menu_label = _('Plan')
    menu_icon = 'kausal-plan'
    add_to_settings_menu = True

    def get_menu_item(self, order=None):
        item = ActivePlanMenuItem(self, order or self.get_menu_order())
        return item


modeladmin_register(ActivePlanAdmin)
