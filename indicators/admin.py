from django.contrib import admin
from django_summernote.admin import SummernoteModelAdmin

from actions.perms import ActionRelatedAdminPermMixin
from .models import Unit, Indicator, IndicatorEstimate, RelatedIndicator, ActionIndicator


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class RelatedIndicatorAdmin(admin.TabularInline):
    model = RelatedIndicator
    fk_name = 'causal_indicator'
    autocomplete_fields = ('effect_indicator',)
    extra = 0


class ActionIndicatorAdmin(ActionRelatedAdminPermMixin, admin.TabularInline):
    model = ActionIndicator
    autocomplete_fields = ('action', 'indicator',)
    extra = 0


@admin.register(Indicator)
class IndicatorAdmin(SummernoteModelAdmin):
    summernote_fields = ('description',)
    autocomplete_fields = ('unit',)
    search_fields = ('name',)
    inlines = [ActionIndicatorAdmin, RelatedIndicatorAdmin]


@admin.register(IndicatorEstimate)
class IndicatorEstimateAdmin(admin.ModelAdmin):
    pass
