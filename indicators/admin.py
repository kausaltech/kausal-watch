from django.contrib import admin
from .models import Unit, Indicator, IndicatorEstimate


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    search_fields = ('name',)


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    autocomplete_fields = ('unit',)


@admin.register(IndicatorEstimate)
class IndicatorEstimateAdmin(admin.ModelAdmin):
    pass
