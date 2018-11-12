from django.contrib import admin
from ordered_model.admin import OrderedTabularInline, OrderedInlineModelAdminMixin, \
    OrderedModelAdmin
from .models import Plan, Action, ActionSchedule, ActionResponsibleParty


class ActionScheduleAdmin(OrderedTabularInline):
    model = ActionSchedule
    extra = 0
    fields = ('name', 'begins_at', 'ends_at', 'move_up_down_links',)
    readonly_fields = ('move_up_down_links',)
    ordering = ('order',)


@admin.register(Plan)
class PlanAdmin(OrderedInlineModelAdminMixin, admin.ModelAdmin):
    inlines = [
        ActionScheduleAdmin
    ]


class ActionResponsiblePartyAdmin(OrderedTabularInline):
    model = ActionResponsibleParty
    extra = 0
    fields = ('org', 'move_up_down_links',)
    readonly_fields = ('move_up_down_links',)
    ordering = ('order',)
    autocomplete_fields = ('org',)


@admin.register(Action)
class ActionAdmin(OrderedModelAdmin):
    filter_horizontal = ('schedule',)
    inlines = [
        ActionResponsiblePartyAdmin
    ]
