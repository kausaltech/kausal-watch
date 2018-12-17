from django.contrib import admin
from .models import Unit, Indicator, IndicatorEstimate, RelatedIndicator
from django_summernote.admin import SummernoteModelAdmin


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class RelatedIndicator(admin.TabularInline):
    model = RelatedIndicator
    fk_name = 'causal_indicator'
    autocomplete_fields = ('effect_indicator',)
    extra = 0


@admin.register(Indicator)
class IndicatorAdmin(SummernoteModelAdmin):
    summernote_fields = ('description',)
    autocomplete_fields = ('unit',)
    search_fields = ('name',)
    inlines = [RelatedIndicator]


@admin.register(IndicatorEstimate)
class IndicatorEstimateAdmin(admin.ModelAdmin):
    pass
