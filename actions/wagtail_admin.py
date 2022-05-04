from django.core.exceptions import ValidationError
from django.forms import ModelForm
from django.utils.translation import gettext
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, ObjectList, TabbedInterface
)
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.menus import ModelAdminMenuItem
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.images.edit_handlers import ImageChooserPanel

from actions.models.action import ActionSchedule
from admin_site.wagtail import (
    ActivePlanEditView, AplansAdminModelForm, AplansCreateView, AplansModelAdmin,
    CondensedInlinePanel, SafeLabelModelAdminMenuItem,
    insert_model_translation_panels
)
from orgs.models import Organization
from people.chooser import PersonChooser

from . import action_admin  # noqa
from . import attribute_type_admin  # noqa
from . import category_admin  # noqa
from .models import ActionImpact, ActionStatus, Plan, PlanFeatures


class PlanEditHandler(TabbedInterface):
    instance: Plan
    form: ModelForm

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
        instance: Plan = super().get_instance()
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


class PlanForm(AplansAdminModelForm):
    def clean_primary_language(self):
        primary_language = self.cleaned_data['primary_language']
        if self.instance and primary_language != self.instance.primary_language:
            raise ValidationError("Changing the primary language is not supported yet.")
        return primary_language


class PlanAdmin(AplansModelAdmin):
    model = Plan
    create_view_class = PlanCreateView
    menu_icon = 'fa-briefcase'
    menu_label = pgettext_lazy('hyphenated', 'Plans')
    menu_order = 500
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('short_name'),
        FieldPanel('identifier'),
        FieldPanel('actions_locked'),
        FieldPanel('site_url'),
        FieldPanel('accessibility_statement_url'),
        FieldPanel('primary_language'),
        FieldPanel('other_languages'),
        CondensedInlinePanel(
            'general_admins_ordered',
            panels=[
                FieldPanel('person', widget=PersonChooser),
            ]
        ),
        ImageChooserPanel('image'),
    ]

    action_status_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
        FieldPanel('is_completed'),
    ]

    action_implementation_phase_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
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

    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        return form_class

    def get_edit_handler(self, instance, request):
        action_status_panels = insert_model_translation_panels(
            ActionStatus, self.action_status_panels, request, instance
        )
        action_implementation_phase_panels = insert_model_translation_panels(
            ActionStatus, self.action_implementation_phase_panels, request, instance
        )
        action_impact_panels = insert_model_translation_panels(
            ActionImpact, self.action_impact_panels, request, instance
        )
        action_schedule_panels = insert_model_translation_panels(
            ActionSchedule, self.action_schedule_panels, request, instance
        )

        panels = insert_model_translation_panels(
            Plan, self.panels, request, instance
        )
        if request.user.is_superuser:
            panels.append(InlinePanel('domains', panels=[
                FieldPanel('hostname'),
                FieldPanel('base_path'),
                FieldPanel('google_site_verification_tag'),
                FieldPanel('matomo_analytics_url'),
            ], heading=_('Domains')))

        tabs = [
            ObjectList(panels, heading=_('Basic information')),
            ObjectList([
                CondensedInlinePanel('action_statuses', panels=action_status_panels, heading=_('Action statuses')),
                CondensedInlinePanel(
                    'action_implementation_phases',
                    panels=action_implementation_phase_panels,
                    heading=_('Action implementation phases')
                ),
                CondensedInlinePanel('action_impacts', panels=action_impact_panels, heading=_('Action impacts')),
                CondensedInlinePanel('action_schedules', panels=action_schedule_panels, heading=_('Action schedules')),
            ], heading=_('Action classifications')),
        ]

        handler = PlanEditHandler(tabs, base_form_class=PlanForm)
        return handler

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(general_admins=person).distinct()
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


# FIXME: This is mostly duplicated in content/admin.py.
class ActivePlanMenuItem(SafeLabelModelAdminMenuItem):
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
    edit_view_class = ActivePlanEditView
    permission_helper_class = ActivePlanPermissionHelper
    menu_label = pgettext_lazy('hyphenated', 'Plan')
    add_to_settings_menu = True

    def get_menu_item(self, order=None):
        item = ActivePlanMenuItem(self, order or self.get_menu_order())
        return item


modeladmin_register(ActivePlanAdmin)


class PlanFeaturesAdmin(AplansModelAdmin):
    model = PlanFeatures
    menu_icon = 'tasks'
    menu_label = pgettext_lazy('hyphenated', 'Plan features')
    menu_order = 501

    superuser_panels = [
        FieldPanel('allow_images_for_actions'),
        FieldPanel('show_admin_link'),
        FieldPanel('public_contact_persons'),
        FieldPanel('has_action_identifiers'),
        FieldPanel('has_action_official_name'),
        FieldPanel('has_action_lead_paragraph'),
        FieldPanel('has_action_primary_orgs'),
    ]

    panels = [
        FieldPanel('enable_search'),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        person = user.get_corresponding_person()
        if not user.is_superuser and person:
            qs = qs.filter(plan__general_admins=person).distinct()
        return qs

    def user_can_create(self):
        return False

    def get_edit_handler(self, instance, request):
        panels = list(self.panels)
        if request.user.is_superuser:
            panels += self.superuser_panels
        handler = ObjectList(panels)
        return handler


# TBD: We might want to keep this for superusers.
# modeladmin_register(PlanFeaturesAdmin)


class ActivePlanFeaturesPermissionHelper(PermissionHelper):
    def user_can_list(self, user):
        return user.is_superuser

    def user_can_create(self, user):
        return False

    def user_can_inspect_obj(self, user, obj):
        return False

    def user_can_delete_obj(self, user, obj):
        return False

    def user_can_edit_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj.plan)


class ActivePlanFeaturesMenuItem(ModelAdminMenuItem):
    def get_context(self, request):
        # When clicking the menu item, use the edit view instead of the index view.
        context = super().get_context(request)
        plan = request.user.get_active_admin_plan()
        context['url'] = self.model_admin.url_helper.get_action_url('edit', plan.features.pk)
        return context

    def is_shown(self, request):
        # The overridden superclass method returns True iff user_can_list from the permission helper returns true. But
        # this menu item is about editing a plan features instance, not listing.
        plan = request.user.get_active_admin_plan()
        return self.model_admin.permission_helper.user_can_edit_obj(request.user, plan.features)


class ActivePlanFeaturesAdmin(PlanFeaturesAdmin):
    edit_view_class = ActivePlanEditView
    permission_helper_class = ActivePlanFeaturesPermissionHelper
    menu_label = pgettext_lazy('hyphenated', 'Plan features')
    add_to_settings_menu = True

    def get_menu_item(self, order=None):
        item = ActivePlanFeaturesMenuItem(self, order or self.get_menu_order())
        return item


modeladmin_register(ActivePlanFeaturesAdmin)


# Monkeypatch Organization to support Wagtail autocomplete
def org_autocomplete_label(self):
    return self.distinct_name


Organization.autocomplete_search_field = 'distinct_name'
Organization.autocomplete_label = org_autocomplete_label
