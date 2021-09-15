from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django_orghierarchy.models import Organization
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, ObjectList, TabbedInterface
)
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.menus import ModelAdminMenuItem
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailautocomplete.edit_handlers import AutocompletePanel

from admin_site.wagtail import (
    AplansCreateView, AplansEditView, AplansModelAdmin, CondensedInlinePanel,
)
from .models import (
    ActionImpact, ActionStatus, Plan
)

from . import category_admin  # noqa
from . import action_admin  # noqa


class PlanEditHandler(TabbedInterface):
    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        return form_class

    def on_form_bound(self):
        super().on_form_bound()
        plan = self.instance
        f = self.form.fields['image']
        if plan.root_collection is None:
            f.queryset = f.queryset.none()
        else:
            f.queryset = f.queryset.model.objects.filter(
                collection__in=plan.root_collection.get_descendants(inclusive=True)
            )


class PlanCreateView(AplansCreateView):
    def get_instance(self):
        instance = super().get_instance()
        if self.request.method == 'POST':
            return instance

        STATUSES = [
            ('not_started', gettext('not started'), False),
            ('in_progress', gettext('in progress'), False),
            ('late', gettext('late'), False),
            ('completed', gettext('completed'), True),
        ]
        instance.action_statuses = [ActionStatus(
            plan=instance,
            identifier=identifier,
            name=name.capitalize(),
            is_completed=is_completed
        ) for identifier, name, is_completed in STATUSES]

        return instance


class PlanAdmin(AplansModelAdmin):
    model = Plan
    create_view_class = PlanCreateView
    menu_icon = 'fa-briefcase'
    menu_label = _('Plans')
    menu_order = 500
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('actions_locked'),
        FieldPanel('allow_images_for_actions'),
        FieldPanel('site_url'),
        FieldPanel('accessibility_statement_url'),
        FieldPanel('primary_language'),
        FieldPanel('other_languages'),
        AutocompletePanel('general_admins'),
        ImageChooserPanel('image'),
        FieldPanel('show_admin_link'),
        FieldPanel('contact_persons_private'),
        FieldPanel('hide_action_identifiers'),
    ]

    action_status_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
        FieldPanel('is_completed'),
    ]

    action_impact_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
    ]

    action_ordering_panels = [
        CondensedInlinePanel('actions', panels=[FieldPanel('identifier'), FieldPanel('name')])
    ]

    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        return form_class

    def get_edit_handler(self, instance, request):
        action_status_panels = self.insert_model_translation_tabs(
            ActionStatus, self.action_status_panels, request, instance
        )
        action_impact_panels = self.insert_model_translation_tabs(
            ActionImpact, self.action_impact_panels, request, instance
        )
        panels = self.insert_model_translation_tabs(
            Plan, self.panels, request, instance
        )
        if request.user.is_superuser:
            panels.append(InlinePanel('domains', panels=[
                FieldPanel('hostname'),
                FieldPanel('google_site_verification_tag'),
                FieldPanel('matomo_analytics_url'),
            ], heading=_('Domains')))

        tabs = [
            ObjectList(panels, heading=_('Basic information')),
            ObjectList([
                CondensedInlinePanel('action_statuses', panels=action_status_panels, heading=_('Action statuses')),
                CondensedInlinePanel('action_impacts', panels=action_impact_panels, heading=_('Action impacts')),

            ], heading=_('Action classifications')),
        ]

        if not instance.actions_locked:
            tabs.append(ObjectList(self.action_ordering_panels, heading=_('Actions')))

        handler = PlanEditHandler(tabs)
        return handler

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        if not user.is_superuser:
            qs = qs.filter(general_admins=user).distinct()
        return qs


# TBD: We might want to keep this for superusers.
# modeladmin_register(PlanAdmin)


# FIXME: This is partly duplicated in content/admin.py.
class ActivePlanPermissionHelper(PermissionHelper):
    def user_can_list(self, user):
        return user.is_superuser

    def user_can_create(self, user):
        return False

    def user_can_inspect_obj(self, user, obj):
        return False

    def user_can_delete_obj(self, user, obj):
        return False

    def user_can_edit_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj)


class ActivePlanEditView(AplansEditView):
    def get_success_url(self):
        # After editing the plan, don't redirect to the index page as AplansEditView does.
        return self.url_helper.get_action_url('edit', self.instance.pk)


# FIXME: This is mostly duplicated in content/admin.py.
class ActivePlanMenuItem(ModelAdminMenuItem):
    def get_context(self, request):
        # When clicking the menu item, use the edit view instead of the index view.
        context = super().get_context(request)
        plan = request.user.get_active_admin_plan()
        context['url'] = self.model_admin.url_helper.get_action_url('edit', plan.pk)
        return context

    def is_shown(self, request):
        # The overridden superclass method returns True iff user_can_list from the permission helper returns true. But
        # this menu item is about editing a plan, not listing.
        plan = request.user.get_active_admin_plan()
        return self.model_admin.permission_helper.user_can_edit_obj(request.user, plan)


class ActivePlanAdmin(PlanAdmin):
    def get_menu_item(self, order=None):
        return ActivePlanMenuItem(self, order or self.get_menu_order())

    edit_view_class = ActivePlanEditView
    permission_helper_class = ActivePlanPermissionHelper
    menu_label = _('Plan')
    add_to_settings_menu = True


modeladmin_register(ActivePlanAdmin)


# Monkeypatch Organization to support Wagtail autocomplete
def org_autocomplete_label(self):
    return self.distinct_name


Organization.autocomplete_search_field = 'distinct_name'
Organization.autocomplete_label = org_autocomplete_label
