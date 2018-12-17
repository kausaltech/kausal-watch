from django import forms
from django.contrib import admin
from ordered_model.admin import OrderedTabularInline, OrderedInlineModelAdminMixin, \
    OrderedModelAdmin
from django_summernote.admin import SummernoteModelAdmin
from django_summernote.widgets import SummernoteInplaceWidget

from .models import Plan, Action, ActionSchedule, ActionResponsibleParty, Scenario, \
    Category, CategoryType, ActionTask, ActionStatus


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


class ActionTaskAdmin(admin.TabularInline):
    model = ActionTask
    extra = 0


@admin.register(Action)
class ActionAdmin(OrderedModelAdmin, SummernoteModelAdmin):
    official_name = forms.CharField(widget=SummernoteInplaceWidget())
    summernote_fields = ('description', 'official_name')
    inlines = [
        ActionResponsiblePartyAdmin, ActionTaskAdmin
    ]


@admin.register(Category)
class CategoryAdmin(OrderedModelAdmin):
    pass
