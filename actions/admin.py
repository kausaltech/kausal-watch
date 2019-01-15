from django.contrib import admin
from ordered_model.admin import OrderedTabularInline, OrderedInlineModelAdminMixin, \
    OrderedModelAdmin
from django_summernote.admin import SummernoteModelAdmin
from django_summernote.widgets import SummernoteWidget

from .models import Plan, Action, ActionSchedule, ActionResponsibleParty, Scenario, \
    Category, CategoryType, ActionTask, ActionStatus
from indicators.admin import ActionIndicatorAdmin


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


@admin.register(Plan)
class PlanAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):
    inlines = [
        ActionStatusAdmin, ActionScheduleAdmin, ScenarioAdmin, CategoryTypeAdmin
    ]


class ActionResponsiblePartyAdmin(OrderedTabularInline):
    model = ActionResponsibleParty
    extra = 0
    # fields = ('org', 'move_up_down_links',)
    # readonly_fields = ('move_up_down_links',)
    fields = ('org',)
    ordering = ('order',)
    autocomplete_fields = ('org',)


class ActionTaskAdmin(admin.StackedInline):
    model = ActionTask
    summernote_fields = ('comment',)
    extra = 0

    def get_formset(self, *args, **kwargs):
        formset = super().get_formset(*args, **kwargs)
        formset.form.base_fields['comment'].widget = SummernoteWidget()
        return formset


@admin.register(Action)
class ActionAdmin(OrderedModelAdmin, SummernoteModelAdmin):
    summernote_fields = ('description', 'official_name')
    search_fields = ('name', 'identifier')
    readonly_fields = (
        'official_name', 'identifier', 'status', 'completion',
        'categories',)
    autocomplete_fields = ('contact_persons',)

    fieldsets = (
        (None, {
            'fields': (
                'plan', 'identifier', 'official_name', 'name', 'description',
                'categories', 'contact_persons',
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


@admin.register(Category)
class CategoryAdmin(OrderedModelAdmin):
    pass
