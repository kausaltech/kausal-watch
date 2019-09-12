from django.contrib import admin
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from admin_numeric_filter.admin import RangeNumericFilter, NumericFilterModelAdmin

from admin_ordering.admin import OrderableAdmin
from image_cropping import ImageCroppingMixin
from ckeditor.widgets import CKEditorWidget

from django_orghierarchy.admin import OrganizationAdmin as DefaultOrganizationAdmin
from django_orghierarchy.models import Organization

from indicators.admin import ActionIndicatorAdmin
from .models import (
    Plan, Action, ActionSchedule, ActionResponsibleParty, Scenario, Category,
    CategoryType, ActionTask, ActionStatus, ActionImpact, ActionContactPerson
)
from .perms import ActionRelatedAdminPermMixin


class ActionScheduleAdmin(admin.TabularInline):
    model = ActionSchedule
    extra = 0
    fields = ('name', 'begins_at', 'ends_at',)


class ScenarioAdmin(admin.StackedInline):
    model = Scenario
    extra = 0


class ActionStatusAdmin(admin.TabularInline):
    model = ActionStatus
    extra = 0


class ActionImpactAdmin(OrderableAdmin, admin.TabularInline):
    model = ActionImpact
    extra = 0
    ordering_field = 'order'
    ordering_field_hide_input = True
    fields = ('order', 'name', 'identifier',)


class CategoryTypeAdmin(admin.StackedInline):
    model = CategoryType
    extra = 0


@admin.register(Plan)
class PlanAdmin(ImageCroppingMixin, admin.ModelAdmin):
    autocomplete_fields = ('general_admins',)
    inlines = [
        ActionStatusAdmin, ActionImpactAdmin, ActionScheduleAdmin, ScenarioAdmin, CategoryTypeAdmin
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


class ActionResponsiblePartyAdmin(ActionRelatedAdminPermMixin, OrderableAdmin, admin.TabularInline):
    model = ActionResponsibleParty
    ordering_field = 'order'
    ordering_field_hide_input = True
    extra = 0
    fields = ('org', 'order',)
    autocomplete_fields = ('org',)
    classes = ('collapse',)


class ActionContactPersonAdmin(ActionRelatedAdminPermMixin, OrderableAdmin, admin.TabularInline):
    model = ActionContactPerson
    ordering_field = 'order'
    ordering_field_hide_input = True
    extra = 0
    fields = ('person', 'order',)
    autocomplete_fields = ('person',)


class ActionTaskAdmin(ActionRelatedAdminPermMixin, admin.StackedInline):
    model = ActionTask
    extra = 0
    fieldsets = (
        (None, {
            'fields': (
                'name', 'completed_at', 'due_at', 'state', 'comment',
            )
        }),
    )

    def get_formset(self, *args, **kwargs):
        formset = super().get_formset(*args, **kwargs)
        formset.form.base_fields['comment'].widget = CKEditorWidget(config_name='lite')
        return formset


class AllActionsFilter(admin.SimpleListFilter):
    title = _('non-modifiable actions')

    parameter_name = 'non_modifiable'

    def lookups(self, request, model_admin):
        return (
            (None, _('Show modifiable')),
            ('yes', _('Show all')),
        )

    def choices(self, cl):
        for lookup, title in self.lookup_choices:
            yield {
                'selected': self.value() == lookup,
                'query_string': cl.get_query_string({
                    self.parameter_name: lookup,
                }, []),
                'display': title,
            }

    def queryset(self, request, queryset):
        if self.value() is None:
            return queryset.modifiable_by(request.user)
        else:
            return queryset


@admin.register(Action)
class ActionAdmin(ImageCroppingMixin, NumericFilterModelAdmin):
    search_fields = ('name', 'identifier')
    list_display = ('__str__', 'impact', 'has_contact_persons', 'active_task_count')

    fieldsets = (
        (None, {
            'fields': (
                'plan', 'identifier', 'official_name', 'name', 'description',
                'categories',
            )
        }),
        (_('Image'), {
            'fields': ('image', 'image_cropping'),
            'classes': ('collapse',)
        }),
        (_('Completion'), {
            'fields': ('status', 'completion'),
            'classes': ('collapse',)
        }),
    )

    inlines = [
        ActionResponsiblePartyAdmin, ActionContactPersonAdmin, ActionIndicatorAdmin, ActionTaskAdmin
    ]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        form.base_fields['description'].widget = CKEditorWidget()

        if obj is not None:
            plan = obj.plan
        else:
            plan = request.user.get_active_admin_plan()

        # Limit choices to what's available in the action plan
        if 'plan' in form.base_fields:
            form.base_fields['plan'].queryset = Plan.objects.filter(id=plan.id)
        if 'status' in form.base_fields:
            form.base_fields['status'].queryset = plan.action_statuses.all()
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

    def get_list_display(self, request):
        user = request.user
        plan = user.get_active_admin_plan()
        list_display = list(self.list_display)
        if user.is_general_admin_for_plan(plan):
            list_display.insert(1, 'internal_priority')
        return list_display

    def get_list_filter(self, request):
        user = request.user
        plan = user.get_active_admin_plan()

        filters = []
        if user.is_general_admin_for_plan(plan):
            filters.append(('internal_priority', RangeNumericFilter))
        else:
            filters.append(AllActionsFilter)
        filters.append('impact')
        return filters

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

    def get_fieldsets(self, request, obj=None):
        user = request.user
        plan = user.get_active_admin_plan()

        fieldsets = list(self.fieldsets)
        if user.is_general_admin_for_plan(plan):
            fieldsets.insert(1, (_('Internal fields'), {
                'fields': ('internal_priority', 'internal_priority_comment', 'impact'),
            }))
            fieldsets.insert(2, (_('Schedule and decision level'), {
                'fields': ('schedule', 'decision_level')
            }))
        return fieldsets

    def get_actions(self, request):
        actions = super().get_actions(request)

        user = request.user
        plan = user.get_active_admin_plan()
        if not user.is_general_admin_for_plan(plan):
            if 'delete_selected' in actions:
                del actions['delete_selected']

        return actions

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

    def save_model(self, request, obj, form, change):
        obj.updated_at = timezone.now()
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(ImageCroppingMixin, admin.ModelAdmin):
    fields = ('type', 'parent', 'identifier', 'name', 'image', 'image_cropping')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(type__plan=plan)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        adminable_plans = request.user.get_adminable_plans()
        plan = request.user.get_active_admin_plan()

        # Limit choices to what's available in the action plan
        field = form.base_fields['type']
        if obj is None:
            field.initial = plan
        field.queryset = field.queryset.filter(plan__in=adminable_plans).distinct()

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
