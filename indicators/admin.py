import pytz
from datetime import date

from django import forms
from django.db.models import Q
from django.contrib import admin
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from ckeditor.widgets import CKEditorWidget

from actions.perms import ActionRelatedAdminPermMixin
from actions.models import Category
from .models import (
    Unit, Indicator, RelatedIndicator, ActionIndicator, IndicatorLevel, IndicatorGoal,
    IndicatorValue
)


LOCAL_TZ = pytz.timezone(settings.TIME_ZONE)


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


class IndicatorLevelAdmin(admin.TabularInline):
    model = IndicatorLevel
    autocomplete_fields = ('indicator',)
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form
        field = form.base_fields['plan']
        admin_plan_ids = [x.id for x in request.user.get_adminable_plans()]
        field.queryset = field.queryset.filter(id__in=admin_plan_ids)
        return formset

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)


class IndicatorGoalAdmin(admin.TabularInline):
    model = IndicatorGoal
    extra = 0
    fields = ('plan', 'date', 'value')

    def get_queryset(self, request):
        plan = request.user.get_active_admin_plan()
        return super().get_queryset(request).filter(plan=plan)

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form

        plan = request.user.get_active_admin_plan()

        field = form.base_fields['date']
        if obj.time_resolution == 'year' and plan.action_schedules.exists():
            schedules = plan.action_schedules.all()
            min_year = min([x.begins_at.year for x in schedules])
            max_year = max([x.ends_at.year for x in schedules])
            field.widget = forms.Select(choices=[('%s-12-31' % y, str(y)) for y in range(min_year, max_year + 1)])

        field = form.base_fields['plan']
        field.initial = plan

        return formset


VALUE_MIN_YEAR = 1990


class IndicatorValueAdmin(admin.TabularInline):
    model = IndicatorValue
    extra = 0
    fields = ('date', 'value')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form

        current_year = date.today().year

        field = form.base_fields['date']
        if obj.time_resolution == 'year':
            years = list(range(VALUE_MIN_YEAR, current_year + 1))
            years.reverse()
            field.widget = forms.Select(choices=[('%s-12-31' % y, str(y)) for y in years])

        return formset


class IndicatorLevelFilter(admin.SimpleListFilter):
    title = _('level')
    parameter_name = 'level'

    def lookups(self, request, model_admin):
        return Indicator.LEVELS

    def queryset(self, request, queryset):
        if not self.value():
            return queryset

        plan = request.user.get_active_admin_plan()
        levels = IndicatorLevel.objects.filter(plan=plan, level=self.value())
        return queryset.filter(levels__in=levels).distinct()


@admin.register(Indicator)
class IndicatorAdmin(admin.ModelAdmin):
    autocomplete_fields = ('unit',)
    search_fields = ('name',)
    list_display = ('name', 'has_data', 'has_graph')
    list_filter = (IndicatorLevelFilter,)
    empty_value_display = _('[nothing]')

    inlines = [IndicatorLevelAdmin, IndicatorGoalAdmin, IndicatorValueAdmin, ActionIndicatorAdmin, RelatedIndicatorAdmin]

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        active_plan = request.user.get_active_admin_plan()

        if obj is None:
            plans = [active_plan]
        else:
            plans = obj.plans.all()

        if 'description' in form.base_fields:
            form.base_fields['description'].widget = CKEditorWidget()

        if 'categories' in form.base_fields:
            categories = Category.objects.filter(type__plan__in=plans).order_by('type', 'identifier').distinct()
            form.base_fields['categories'].queryset = categories

        return form

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)
        if obj is None:
            for inline in list(inlines):
                if isinstance(inline, IndicatorGoalAdmin):
                    inlines.remove(inline)
        return inlines

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(Q(plans=plan) | Q(plans__isnull=True)).distinct()
