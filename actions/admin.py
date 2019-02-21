from django.contrib import admin
from ordered_model.admin import OrderedTabularInline, OrderedInlineModelAdminMixin, \
    OrderedModelAdmin
from django_summernote.admin import SummernoteModelAdmin
from django_summernote.widgets import SummernoteWidget
from image_cropping import ImageCroppingMixin

from django_orghierarchy.admin import OrganizationAdmin as DefaultOrganizationAdmin
from django_orghierarchy.models import Organization

from indicators.admin import ActionIndicatorAdmin
from .models import Plan, Action, ActionSchedule, ActionResponsibleParty, Scenario, \
    Category, CategoryType, ActionTask, ActionStatus
from .perms import ActionRelatedAdminPermMixin


class ActionScheduleAdmin(OrderedTabularInline):
    model = ActionSchedule
    extra = 0
    fields = ('name', 'begins_at', 'ends_at', 'move_up_down_links',)
    readonly_fields = ('move_up_down_links',)
    ordering = ('order',)


class ScenarioAdmin(admin.StackedInline):
    model = Scenario
    extra = 0


class ActionStatusAdmin(admin.TabularInline):
    model = ActionStatus
    extra = 0


class CategoryTypeAdmin(admin.StackedInline):
    model = CategoryType
    extra = 0

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)


@admin.register(Plan)
class PlanAdmin(ImageCroppingMixin, OrderedInlineModelAdminMixin, admin.ModelAdmin):
    autocomplete_fields = ('general_admins',)
    inlines = [
        ActionStatusAdmin, ActionScheduleAdmin, ScenarioAdmin, CategoryTypeAdmin
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plans = request.user.get_adminable_plans()
        return qs.filter(id__in=[x.id for x in plans])

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        user = request.user
        return user.is_general_admin_for_plan(obj)

    def has_delete_permission(self, request, obj=None):
        if not super().has_delete_permission(request, obj):
            return False
        if obj and obj.actions_locked:
            return False
        return True


class ActionResponsiblePartyAdmin(ActionRelatedAdminPermMixin, OrderedTabularInline):
    model = ActionResponsibleParty
    extra = 0
    # fields = ('org', 'move_up_down_links',)
    # readonly_fields = ('move_up_down_links',)
    fields = ('org',)
    ordering = ('order',)
    autocomplete_fields = ('org',)


class ActionTaskAdmin(ActionRelatedAdminPermMixin, admin.StackedInline):
    model = ActionTask
    summernote_fields = ('comment',)
    extra = 0

    def get_formset(self, *args, **kwargs):
        formset = super().get_formset(*args, **kwargs)
        formset.form.base_fields['comment'].widget = SummernoteWidget()
        return formset


@admin.register(Action)
class ActionAdmin(ImageCroppingMixin, OrderedModelAdmin, SummernoteModelAdmin):
    summernote_fields = ('description', 'official_name')
    search_fields = ('name', 'identifier')
    autocomplete_fields = ('contact_persons',)
    list_display = ('__str__', 'plan')

    fieldsets = (
        (None, {
            'fields': (
                'plan', 'identifier', 'official_name', 'name', 'description',
                'categories', 'contact_persons', 'image', 'image_cropping',
            )
        }),
        (None, {
            'fields': ('status', 'completion')
        }),
        (None, {
            'fields': ('schedule', 'decision_level')
        }),
    )

    inlines = [
        ActionResponsiblePartyAdmin, ActionIndicatorAdmin, ActionTaskAdmin
    ]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        if obj is not None:
            plan = obj.plan
        else:
            plan = request.user.get_active_admin_plan()

        # Limit choices to what's available in the action plan
        if 'plan' in form.base_fields:
            form.base_fields['plan'].queryset = Plan.objects.filter(id=plan.id)
        if 'schedule' in form.base_fields:
            form.base_fields['schedule'].queryset = plan.action_schedules.all()
        if 'decision_level' in form.base_fields:
            form.base_fields['decision_level'].queryset = plan.action_decision_levels.all()
        if 'categories' in form.base_fields:
            categories = Category.objects.filter(type__plan=plan).order_by('identifier')
            form.base_fields['categories'].queryset = categories

        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = ['completion']
        LOCKED_FIELDS = [
            'official_name', 'identifier', 'status',
            'completion', 'categories',
        ]
        if obj is None:
            # This is an add request
            return readonly_fields

        # If the actions for the plan are locked, restrict modify
        # access to some official fields.
        if obj.plan.actions_locked:
            readonly_fields = readonly_fields + LOCKED_FIELDS

        return readonly_fields

    def has_view_permission(self, request, obj=None):
        if not super().has_view_permission(request, obj):
            return False

        # The user has view permission to all actions if he is either
        # a general admin for actions or a contact person for any
        # actions.
        user = request.user
        if user.is_superuser or user.has_perm('actions.admin_action'):
            return True

        return user.is_contact_person_for_action(None)

    def has_change_permission(self, request, obj=None):
        if not super().has_change_permission(request, obj):
            return False
        user = request.user
        return user.can_modify_action(obj)

    def has_delete_permission(self, request, obj=None):
        user = request.user
        if not user.can_modify_action(obj):
            return False

        if obj is not None:
            plan = obj.plan
            if plan.actions_locked:
                return False

        return True

    def has_add_permission(self, request):
        if not super().has_add_permission(request):
            return False

        user = request.user
        if not user.can_modify_action():
            return False

        plan = user.get_active_admin_plan()
        if plan.actions_locked:
            return False

        return True


@admin.register(Category)
class CategoryAdmin(ImageCroppingMixin, OrderedModelAdmin):
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(type__plan=plan)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        plan = request.user.get_active_admin_plan()

        # Limit choices to what's available in the action plan
        field = form.base_fields['type']
        field.queryset = field.queryset.filter(plan=plan).distinct()

        field = form.base_fields['parent']
        if obj is not None:
            filters = dict(type=obj.type)
        else:
            filters = dict(type__plan=plan)
        field.queryset = field.queryset.filter(**filters).distinct()
        return form

    def has_delete_permission(self, request, obj=None):
        user = request.user
        plan = user.get_active_admin_plan()
        if plan is None or plan.actions_locked:
            return False

        return True


admin.site.unregister(Organization)


@admin.register(Organization)
class OrganizationAdmin(DefaultOrganizationAdmin):
    search_fields = ('name', 'abbreviation')

    def get_queryset(self, request):
        # The default OrganizationAdmin is buggy
        qs = admin.ModelAdmin.get_queryset(self, request).filter(dissolution_date=None)
        return qs

    def get_actions(self, request):
        return admin.ModelAdmin.get_actions(self, request)
