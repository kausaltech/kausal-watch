from django.contrib import admin
from ordered_model.admin import OrderedTabularInline, OrderedInlineModelAdminMixin, \
    OrderedModelAdmin
from markdownx.admin import MarkdownxModelAdmin
from .models import Plan, Action, ActionSchedule, ActionResponsibleParty, Scenario


class ActionScheduleAdmin(OrderedTabularInline):
    model = ActionSchedule
    extra = 0
    fields = ('name', 'begins_at', 'ends_at', 'move_up_down_links',)
    readonly_fields = ('move_up_down_links',)
    ordering = ('order',)


class ScenarioAdmin(admin.StackedInline):
    model = Scenario
    extra = 0


@admin.register(Plan)
class PlanAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):
    inlines = [
        ActionScheduleAdmin, ScenarioAdmin
    ]


class ActionResponsiblePartyAdmin(OrderedTabularInline):
    model = ActionResponsibleParty
    extra = 0
    # fields = ('org', 'move_up_down_links',)
    # readonly_fields = ('move_up_down_links',)
    fields = ('org',)
    ordering = ('order',)
    autocomplete_fields = ('org',)


@admin.register(Action)
class ActionAdmin(OrderedModelAdmin, MarkdownxModelAdmin):
    inlines = [
        ActionResponsiblePartyAdmin
    ]
