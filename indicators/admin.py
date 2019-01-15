from django.contrib import admin
from .models import Unit, Indicator, IndicatorEstimate, RelatedIndicator, ActionIndicator
from django_summernote.admin import SummernoteModelAdmin


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class RelatedIndicatorAdmin(admin.TabularInline):
    model = RelatedIndicator
    fk_name = 'causal_indicator'
    autocomplete_fields = ('effect_indicator',)
    extra = 0


class ActionIndicatorAdmin(admin.TabularInline):
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
