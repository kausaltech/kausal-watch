import pytz
from datetime import date

from django import forms
from django.db.models import Q
from django.contrib import admin
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from ckeditor.widgets import CKEditorWidget
from admin_ordering.admin import OrderableAdmin

from admin_site.admin import AplansImportExportMixin, AplansModelAdmin
from actions.perms import ActionRelatedAdminPermMixin
from .resources import IndicatorResource
from .models import (
    Unit, Indicator, RelatedIndicator, ActionIndicator, IndicatorLevel, IndicatorGoal,
    IndicatorValue, Quantity, IndicatorContactPerson, Dataset, DatasetLicense
)


LOCAL_TZ = pytz.timezone(settings.TIME_ZONE)


@admin.register(Unit)
class UnitAdmin(admin.ModelAdmin):
    list_display = ('name', 'short_name', 'verbose_name')
    search_fields = ('name',)


@admin.register(Quantity)
class QuantityAdmin(admin.ModelAdmin):
    search_fields = ('name',)


class RelatedIndicatorAdmin(admin.TabularInline):
    model = RelatedIndicator
    extra = 0

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form
        field = form.base_fields[self.autocomplete_fields[0]]
        plan = request.user.get_active_admin_plan()
        field.queryset = field.queryset.filter(levels__plan=plan)
        return formset

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        fname = '%s__levels__plan' % self.autocomplete_fields[0]
        return qs.filter(**{fname: plan}).distinct()


class RelatedEffectIndicatorAdmin(RelatedIndicatorAdmin):
    fk_name = 'causal_indicator'
    autocomplete_fields = ('effect_indicator',)
    verbose_name = _('Downstream indicator')
    verbose_name_plural = _('Downstream indicators')


class RelatedCausalIndicatorAdmin(RelatedIndicatorAdmin):
    fk_name = 'effect_indicator'
    autocomplete_fields = ('causal_indicator',)
    verbose_name = _('Upstream indicator')
    verbose_name_plural = _('Upstream indicators')


class ActionIndicatorAdmin(ActionRelatedAdminPermMixin, admin.TabularInline):
    model = ActionIndicator
    autocomplete_fields = ('action', 'indicator',)
    extra = 0
    verbose_name = _('Indicator action')
    verbose_name_plural = _('Indicator actions')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(action__plan=plan)


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
    fields = ('date', 'value', 'scenario')

    def get_queryset(self, request):
        plan = request.user.get_active_admin_plan()
        return super().get_queryset(request).filter(plan=plan)

    def get_formset(self, request, obj=None, **kwargs):
        plan = request.user.get_active_admin_plan()
        if plan.scenarios.count() == 0:
            if 'scenario' in self.fields:
                fields = set(self.fields)
                fields.remove('scenario')
                self.fields = tuple(fields)

        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form

        field = form.base_fields.get('scenario')
        if field is not None:
            field.queryset = plan.scenarios.all()

        field = form.base_fields['date']
        if obj is not None and obj.time_resolution == 'year' and plan.action_schedules.exists():
            schedules = plan.action_schedules.all()
            min_year = min([x.begins_at.year for x in schedules])
            max_year = max([x.ends_at.year for x in schedules])
            field.widget = forms.Select(choices=[('%s-12-31' % y, str(y)) for y in range(min_year, max_year + 1)])

        return formset


VALUE_MIN_YEAR = 1970


class IndicatorValueAdmin(admin.TabularInline):
    model = IndicatorValue
    extra = 0
    fields = ('date', 'value')

    def get_formset(self, request, obj=None, **kwargs):
        formset = super().get_formset(request, obj, **kwargs)
        form = formset.form

        current_year = date.today().year

        field = form.base_fields['date']
        if obj is not None and obj.time_resolution == 'year':
            years = list(range(VALUE_MIN_YEAR, current_year + 1))
            years.reverse()
            field.widget = forms.Select(choices=[('%s-12-31' % y, str(y)) for y in years])

        return formset

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.filter(categories__isnull=True).distinct()


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


class DisconnectedIndicatorFilter(admin.SimpleListFilter):
    title = _('Disconnected indicators')
    parameter_name = 'disconnected'

    def lookups(self, request, model_admin):
        return (
            (None, _('No')),
            ('1', _('Yes')),
        )

    def queryset(self, request, queryset):
        if not self.value():
            plan = request.user.get_active_admin_plan()
            return queryset.filter(levels__plan=plan)
        return queryset

    def choices(self, changelist):
        for lookup, title in self.lookup_choices:
            if lookup is not None:
                lookup = str(lookup)
            yield {
                'selected': self.value() == lookup,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }


class IndicatorContactPersonAdmin(OrderableAdmin, admin.TabularInline):
    model = IndicatorContactPerson
    ordering_field = 'order'
    ordering_field_hide_input = True
    extra = 0
    fields = ('person', 'order',)
    autocomplete_fields = ('person',)


@admin.register(Indicator)
class IndicatorAdmin(AplansImportExportMixin, AplansModelAdmin):
    autocomplete_fields = ('unit', 'datasets', 'quantity')
    search_fields = ('name',)
    list_display = ('name', 'unit', 'quantity', 'has_data',)
    list_filter = (IndicatorLevelFilter, DisconnectedIndicatorFilter)
    empty_value_display = _('[nothing]')

    inlines = [
        IndicatorLevelAdmin, IndicatorContactPersonAdmin, IndicatorGoalAdmin,
        IndicatorValueAdmin, ActionIndicatorAdmin, RelatedCausalIndicatorAdmin,
        RelatedEffectIndicatorAdmin
    ]

    # For import/export
    resource_class = IndicatorResource

    def get_list_display(self, request):
        plan = request.user.get_active_admin_plan()

        def has_goals(obj):
            return obj.goals.filter(plan=plan).exists()
        has_goals.short_description = _('has goals')
        has_goals.boolean = True

        ret = super().get_list_display(request)
        return ret + (has_goals, 'has_datasets',)

    def get_form(self, request, obj=None, **kwargs):
        plan = request.user.get_active_admin_plan()

        # Override the form class with a dynamic class that includes our
        # type-specific category fields.
        self.form = type(
            'IndicatorAdminForm',
            (forms.ModelForm,),
            self._get_category_fields(plan, obj, with_initial=True),
        )

        form = super().get_form(request, obj, **kwargs)

        if 'description' in form.base_fields:
            form.base_fields['description'].widget = CKEditorWidget()

        return form

    def get_fieldsets(self, request, obj=None):
        fieldsets = super().get_fieldsets(request, obj)

        plan = request.user.get_active_admin_plan()
        category_fields = list(self._get_category_fields(plan, obj).keys())

        fs = fieldsets[0][1]
        for field_name in ['categories', *category_fields]:
            if field_name in fs['fields']:
                fs['fields'].remove(field_name)

        fieldsets.append(
            (_('Categories'), dict(fields=(x for x in category_fields)))
        )
        return fieldsets

    def get_inline_instances(self, request, obj=None):
        inlines = super().get_inline_instances(request, obj)
        # If we're adding a new object, we don't show the entries for goals
        # and values yet, because their rendering depends on what time resolution
        # the indicator has.
        if obj is None:
            for inline in list(inlines):
                if isinstance(inline, IndicatorGoalAdmin):
                    inlines.remove(inline)
                if isinstance(inline, IndicatorValueAdmin):
                    inlines.remove(inline)
        return inlines

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(Q(plans=plan) | Q(plans__isnull=True)).distinct().select_related('unit', 'quantity')

    def save_formset(self, request, form, formset, change):
        instances = formset.save(commit=False)
        plan = request.user.get_active_admin_plan()
        for obj in formset.deleted_objects:
            obj.delete()
        for instance in instances:
            if isinstance(instance, IndicatorGoal):
                if not instance.plan_id:
                    instance.plan = plan
            instance.save()
        formset.save_m2m()

    def get_actions(self, request):
        actions = super().get_actions(request)

        # Remove the 'delete selected' action to prevent catastrophic mistakes.
        if 'delete_selected' in actions:
            del actions['delete_selected']

        return actions

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        obj.set_latest_value()
        obj.save(update_fields=['latest_value'])
        actions = obj.related_actions.filter(indicates_action_progress=True)
        for act_ind in actions:
            act = act_ind.action
            act.recalculate_status()

        plan = request.user.get_active_admin_plan()
        for field_name, field in self._get_category_fields(plan, obj).items():
            if field_name not in form.cleaned_data:
                continue
            cat_type = field.category_type
            existing_cats = set(obj.categories.filter(type=cat_type))
            new_cats = set(form.cleaned_data[field_name])
            for cat in existing_cats - new_cats:
                obj.categories.remove(cat)
            for cat in new_cats - existing_cats:
                obj.categories.add(cat)


@admin.register(Dataset)
class DatasetAdmin(AplansModelAdmin):
    autocomplete_fields = ('owner',)
    search_fields = ('name',)


@admin.register(DatasetLicense)
class DatasetLicenseAdmin(AplansModelAdmin):
    pass
