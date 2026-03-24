from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from django import forms
from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.forms import inlineformset_factory
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _, ngettext_lazy, pgettext_lazy
from wagtail import hooks
from wagtail.admin.panels import (
    FieldPanel,
    FieldRowPanel,
    HelpPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
)

from dal import autocomplete, forward as dal_forward
from generic_chooser.views import ModelChooserViewSet
from generic_chooser.widgets import AdminChooser
from wagtail_color_panel.edit_handlers import NativeColorPanel
from wagtail_modeladmin.helpers.permission import PermissionHelper
from wagtail_modeladmin.options import ModelAdminGroup
from wagtail_modeladmin.views import DeleteView

from kausal_common.datasets.models import (
    DataPoint,
    Dataset,
    DatasetMetric,
    DatasetMetricComputation,
    DatasetSchema,
    DatasetSchemaScope,
)
from kausal_common.people.chooser import PersonChooser
from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request, get_admin_cache
from aplans.extensions import modeladmin_register
from aplans.wagtail_utils import _get_category_fields

from actions.models.plan import Plan
from admin_site.utils import admin_req
from admin_site.wagtail import (
    AplansAdminModelForm,
    AplansCreateView,
    AplansEditView,
    AplansIndexView,
    AplansModelAdmin,
    AplansTabbedInterface,
    BuiltInFieldCustomizationAwareEditHandlerMixin,
    CondensedInlinePanel,
    CustomizableBuiltInFieldPanel,
    InitializeFormWithInitialPlanMixin,
    InitializeFormWithPlanMixin,
    get_translation_tabs,
)
from indicators.chooser import DimensionChooser, IndicatorValueChooser
from indicators.panels import IndicatorMetricsInlinePanel
from orgs.models import Organization

from .models import CommonIndicator, Dimension, Indicator, IndicatorLevel, Quantity, Unit
from .models.goal_data_point import IndicatorGoalDataPoint

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.admin.panels.base import Panel

    from users.models import User


class UnitSuffixWidget(autocomplete.ListSelect2):
    """Select2 autocomplete for unit strings with an inline "per X" suffix."""

    def __init__(self, suffix: str = '', **kwargs):
        kwargs.setdefault('url', 'metric-unit-autocomplete')
        super().__init__(**kwargs)
        self.suffix = suffix

    def render(self, name, value, attrs=None, renderer=None):
        input_html = super().render(name, value, attrs, renderer)
        if not self.suffix:
            return input_html
        return format_html(
            '<div style="display:flex;align-items:center;gap:0.5em">'
            '{}<span style="white-space:nowrap">per <strong>{}</strong></span>'
            '</div>',
            input_html,
            self.suffix,
        )


class FactorForm(forms.ModelForm):
    """
    Form for a single factor (DatasetMetric) with extra fields for the result metric.

    Each factor implicitly creates a computation: indicator_values x factor = result.
    The user enters the factor unit as a numerator (e.g. "tCO2e"); the implicit
    denominator is the indicator's unit ("per vehicle"). The result unit equals
    the factor's entered unit (since indicator_unit cancels out in the multiplication).
    """

    class Meta:
        model = DatasetMetric
        fields = ['label', 'unit']

    result_label = forms.CharField(
        required=True,
        label=_('Result'),
        help_text=_('The name of the computed value (indicator data \u00d7 factor) shown in charts, e.g. "Vehicle emissions"'),
    )

    def __init__(self, *args, indicator_unit_label: str = '', indicator_unit_short: str = '', **kwargs):
        super().__init__(*args, **kwargs)
        self._indicator_unit_label = indicator_unit_label
        self._indicator_unit_short = indicator_unit_short
        # Strip the "/{indicator_unit}" denominator for display
        initial = self.instance.unit if self.instance.pk else ''
        if initial and indicator_unit_short:
            suffix = f'/{indicator_unit_short}'
            initial = initial.removesuffix(suffix)
        # Replace the model's CharField with a Select2 autocomplete that allows
        # free-text entry. We must seed the current value as a choice so Select2
        # can render it, and set it as initial so it's selected on load.
        choices = [initial] if initial else []
        unit_field = autocomplete.Select2ListCreateChoiceField(
            required=False,
            widget=UnitSuffixWidget(suffix=indicator_unit_label),
            choice_list=choices,
        )
        self.fields['unit'] = unit_field
        # Force the rendered value — in a ModelForm the value normally comes from
        # the model instance, but we replaced the field so we need to set initial
        # (used when the form is unbound).
        self.initial['unit'] = initial
        # Pre-fill result_label from existing computation
        if self.instance.pk:
            comp = (
                DatasetMetricComputation.objects
                .filter(
                    operand_b=self.instance,
                    operand_a__isnull=True,
                )
                .select_related('target_metric')
                .first()
            )
            if comp:
                self.fields['result_label'].initial = comp.target_metric.label

    def save(self, commit=True):
        # Append "/{indicator_unit}" to form the compound factor unit before saving
        numerator = self.cleaned_data.get('unit', '').strip()
        if numerator and self._indicator_unit_short:
            self.instance.unit = f'{numerator}/{self._indicator_unit_short}'
        else:
            self.instance.unit = numerator
        return super().save(commit=commit)


def _make_factor_formset(  # noqa: ANN202
    schema,
    indicator_unit_label: str,
    indicator_unit_short: str,
    data=None,
):
    """Create the factor (DatasetMetric) formset with extra result fields."""
    FactorFormSet = inlineformset_factory(
        DatasetSchema,
        DatasetMetric,
        form=FactorForm,
        fields=['label', 'unit'],
        extra=0,
        can_delete=True,
    )
    kwargs: dict[str, Any] = {
        'instance': schema,
        'prefix': 'metrics',
        'form_kwargs': {
            'indicator_unit_label': indicator_unit_label,
            'indicator_unit_short': indicator_unit_short,
        },
    }
    if data:
        kwargs['data'] = data
    formset = FactorFormSet(**kwargs)
    # Exclude computed metrics (auto-created targets) from the queryset so
    # they don't appear as editable factor rows.
    if schema is not None:
        formset.queryset = formset.queryset.filter(computed_by__isnull=True)  # type: ignore[union-attr]
    return formset


class DisconnectedIndicatorFilter(SimpleListFilter):
    title = _('Show indicators')
    parameter_name = 'disconnected'

    def lookups(self, request, model_admin):
        return (
            (None, _('in active plan')),
            ('2', _('not in active plan')),
            ('1', _('all')),
        )

    def queryset(self, request, queryset):
        plan = admin_req(request).user.get_active_admin_plan()
        if self.value() == '1':
            pass
        elif self.value() == '2':
            queryset = queryset.exclude(id__in=IndicatorLevel.objects.filter(plan=plan).values_list('indicator_id'))
        else:
            queryset = queryset.filter(levels__plan=plan)
        return queryset

    def choices(self, changelist):
        assert self.parameter_name is not None
        for lookup, title in self.lookup_choices:
            if lookup is not None:
                lookup = str(lookup)
            yield {
                'selected': self.value() == lookup,
                'query_string': changelist.get_query_string({self.parameter_name: lookup}),
                'display': title,
            }


class IndicatorPermissionHelper(PermissionHelper[Indicator]):
    def user_can_inspect_obj(self, user: User, obj: Indicator) -> bool:
        if not super().user_can_inspect_obj(user, obj):
            return False

        # The user has view permission to all actions if he is either
        # a general admin for actions or a contact person for any
        # actions.
        if user.is_superuser:
            return True

        adminable_plans = user.get_adminable_plans()
        obj_plans = obj.plans.all()
        return any(plan in obj_plans for plan in adminable_plans)

    def user_can_edit_obj(self, user: User, obj: Indicator):
        if not super().user_can_edit_obj(user, obj):
            return False
        if user.is_superuser:
            return True

        for plan in obj.get_plans_with_access():
            if user.is_general_admin_for_plan(plan):
                return True

        return user.is_contact_person_for_indicator(obj) or user.is_organization_admin_for_indicator(obj)

    def user_can_delete_obj(self, user: User, obj: Indicator):
        if not super().user_can_delete_obj(user, obj):
            return False

        obj_plans = obj.plans.all()
        admin_for_all = all(user.is_general_admin_for_plan(plan) for plan in obj_plans)
        if not admin_for_all:
            return False

        return True

    def user_can_create(self, user):
        if not super().user_can_create(user):
            return False

        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            return True
        return False


class QuantityChooserViewSet(ModelChooserViewSet[Quantity]):
    icon = 'kausal-dimension'  # FIXME
    model = Quantity
    page_title = _('Choose a quantity')
    per_page = 10
    order_by = 'name'
    fields = ['name']


class QuantityChooser(AdminChooser):
    choose_one_text = _('Choose a quantity')
    choose_another_text = _('Choose another quantity')
    link_to_chosen_text = _('Edit this quantity')
    model = Quantity
    choose_modal_url_name = 'quantity_chooser:choose'


@hooks.register('register_admin_viewset')
def register_quantity_chooser_viewset():
    return QuantityChooserViewSet('quantity_chooser', url_prefix='quantity-chooser')


class DimensionCreateView(AplansCreateView[Dimension]):
    def form_valid(self, form, *args, **kwargs):
        response = super().form_valid(form, *args, **kwargs)
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        dimension = form.instance

        if plan:
            from indicators.models import PlanDimension

            PlanDimension.objects.get_or_create(plan=plan, dimension=dimension)

        return response


class DimensionDeleteView(DeleteView[Dimension]):
    def post(self, request, *args, **kwargs):
        dimension = self.instance
        current_plan = request.user.get_active_admin_plan()
        assert dimension is not None
        other_plans = dimension.plans.exclude(plan=current_plan)
        if other_plans.exists():
            messages.error(
                request,
                _('Cannot delete dimension "%(dimension)s" at this time, please contact support.')
                % {
                    'dimension': dimension.name,
                },
            )
            return redirect(self.index_url)

        return super().post(request, *args, **kwargs)


class DimensionAdmin(AplansModelAdmin[Dimension]):
    model = Dimension
    menu_order = 4
    menu_icon = 'kausal-dimension'
    menu_label = _('Indicator dimensions')
    list_display = ('name',)
    create_view_class = DimensionCreateView
    delete_view_class = DimensionDeleteView

    panels = [
        FieldPanel('name'),
        InlinePanel(
            'categories',
            panels=[
                FieldPanel('name'),
                NativeColorPanel('default_color'),
            ],
            heading=_('Categories'),
        ),
    ]

    def get_queryset(self, request):
        plan = request.user.get_active_admin_plan()
        return super().get_queryset(request).filter(plans__plan=plan)


class QuantityForm(AplansAdminModelForm[Quantity]):
    pass


class QuantityAdmin(AplansModelAdmin[Quantity]):
    model = Quantity
    menu_icon = 'kausal-dimension'  # FIXME
    menu_order = 6
    menu_label = _('Quantities')
    list_display = ('name_i18n',)

    panels = [
        FieldPanel('name'),
    ]

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()
        tabs = [
            ObjectList(self.panels, heading=_('General')),
            *get_translation_tabs(instance, request, include_all_languages=True),
        ]
        return AplansTabbedInterface(tabs, base_form_class=QuantityForm)

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('name_i18n')


class UnitForm(AplansAdminModelForm[Unit]):
    pass


class UnitAdmin(AplansModelAdmin[Unit]):
    model = Unit
    menu_icon = 'kausal-dimension'  # FIXME
    menu_order = 5
    menu_label = _('Units')
    list_display = ('name', 'short_name')

    panels = [
        FieldPanel('name'),
        FieldPanel('short_name'),
        FieldPanel('verbose_name'),
        FieldPanel('verbose_name_plural'),
    ]

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()
        tabs = [
            ObjectList(self.panels, heading=_('General')),
            *get_translation_tabs(instance, request, include_all_languages=True),
        ]
        return AplansTabbedInterface(tabs, base_form_class=UnitForm)


class IndicatorForm(AplansAdminModelForm[Indicator]):
    LEVEL_CHOICES = (('', _('[not in active plan]')),) + Indicator.LEVELS

    level = forms.ChoiceField(choices=LEVEL_CHOICES, required=False)

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        self.initial_plan_id = kwargs.pop('initial_plan_id', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk is not None:
            # We are editing an existing indicator. If the indicator is in the
            # active plan, set this form's `level` field to the proper value.
            try:
                indicator_level = IndicatorLevel.objects.get(indicator=self.instance, plan=self.plan)
                self.fields['level'].initial = indicator_level.level
            except IndicatorLevel.DoesNotExist:
                # Indicator is not in active plan
                pass

        # Inject the metrics formset into self.formsets so that
        # IndicatorMetricsInlinePanel can pick it up via self.form.formsets['metrics'].
        schema = self.instance.dataset_schema if self.instance.pk else None
        indicator_unit_label = ''
        indicator_unit_short = ''
        if self.instance.pk and self.instance.unit:
            unit = self.instance.unit
            indicator_unit_label = unit.name or unit.short_name or ''
            indicator_unit_short = unit.short_name or unit.name or ''
        self.formsets['metrics'] = _make_factor_formset(  # type: ignore[index]
            schema,
            indicator_unit_label,
            indicator_unit_short,
            data=self.data or None,
        )

    def get_dimension_ids_from_formset(self):
        if 'dimensions' not in self.formsets:
            return None
        fs = self.formsets['dimensions']
        if not hasattr(fs, 'cleaned_data'):
            return None
        sorted_form_data = sorted(fs.cleaned_data, key=lambda d: d.get('ORDER', 0))
        return [d['dimension'].id for d in sorted_form_data if not d.get('DELETE')]

    def clean_organization(self):
        # Disallow changing organization to one with different language for now because which language variants of
        # translatable form fields are present depends on the organization's language.
        organization = self.cleaned_data['organization']
        if self.instance.pk is not None and self.instance.organization.primary_language != organization.primary_language:
            raise ValidationError(
                _('Changing the organization to one with a different primary language is currently not supported'),
            )
        return organization

    def clean(self):
        super().clean()

        common = self.cleaned_data.get('common')
        # Dimensions cannot be accessed from self.instance.dimensions yet
        new_dimensions = self.get_dimension_ids_from_formset()

        if common and new_dimensions is not None:
            common_indicator_dimensions = list(common.dimensions.values_list('dimension', flat=True))
            if new_dimensions != common_indicator_dimensions:
                # FIXME: At the moment there is a bug presumably in CondensedInlinePanel. If you try to remove the
                # dimensions of an indicator whose common indicator has dimensions, you will correctly get a validation
                # error and are presented again with the form, which will have the old dimensions in it. If you try to
                # save again without changing anything, the forms will the dimension formset will have 'DELETE' set to
                # true. Another weird issue: If, for example you add a new dimension to the indicator that's not in the
                # common indicator, you'll get this validation error but the condensed inline panel will be gone. WTF?
                # This may also affect CommonIndicatorForm.
                raise ValidationError(_('Dimensions must be the same as in common indicator'))

        if not self.formsets['metrics'].is_valid():
            raise ValidationError(_('Please correct the errors in the factors section.'))

        self._validate_no_data_in_deleted_factors()

        return self.cleaned_data

    def _validate_no_data_in_deleted_factors(self) -> None:
        """Prevent deletion of factors that have data points."""
        metrics_formset = self.formsets['metrics']
        for form in metrics_formset.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data.get('DELETE'):
                continue
            factor = form.instance
            if not factor.pk:
                continue
            has_data = (
                DataPoint.objects.filter(metric=factor).exists() or IndicatorGoalDataPoint.objects.filter(metric=factor).exists()
            )
            if has_data:
                raise ValidationError(
                    _(
                        'The factor "%(label)s" has data and cannot be deleted. '
                        'Delete its data points first in the dataset editor.'
                    )
                    % {'label': factor.label},
                )

    @staticmethod
    def _has_new_factors(metrics_formset) -> bool:
        """Check if the factors formset has any new (non-deleted) factors."""
        if not metrics_formset.is_valid():
            return False
        return any(form_data and not form_data.get('DELETE') for form_data in metrics_formset.cleaned_data)

    def _ensure_dataset_schema(self, indicator: Indicator) -> DatasetSchema:
        """Auto-create a DatasetSchema for the indicator if it doesn't have one."""
        if indicator.dataset_schema is not None:
            return indicator.dataset_schema

        schema = DatasetSchema.objects.create(
            name=str(_('Indicator factors')),
            time_resolution=DatasetSchema.TimeResolution.YEARLY,
        )
        # Scope the schema to the indicator instance (per indicators.md architecture)
        indicator_ct = ContentType.objects.get_for_model(Indicator)
        DatasetSchemaScope.objects.create(
            schema=schema,
            scope_content_type=indicator_ct,
            scope_id=indicator.pk,
        )
        indicator.dataset_schema = schema
        indicator.save(update_fields=['dataset_schema'])
        return schema

    def save(self, commit=True):
        initial_plan_id = self.initial_plan_id
        # Use initial_plan_id to detect mismatch between the active plan and the initial plan on form load.
        if initial_plan_id and str(initial_plan_id) != str(self.plan.id):
            initial_plan = Plan.objects.get(id=initial_plan_id)

            request = ctx_request.get()
            messages.add_message(
                request,
                messages.WARNING,
                _(
                    'While editing this indicator you have switched to a different plan. '
                    'This indicator was still saved with the original plan "%s".'
                )
                % initial_plan.name,
            )
            self.plan = initial_plan

        if self.instance.organization_id is None:
            self.instance.organization = self.plan.organization
        old_dimensions = list(self.instance.dimensions.values_list('dimension', flat=True))
        new_dimensions = self.get_dimension_ids_from_formset()
        if new_dimensions is not None and old_dimensions != new_dimensions:
            # Hopefully the user hasn't changed the dimensions by accident because now it's bye-bye, indicator values
            self.instance.latest_value = None
            self.instance.save()
            self.instance.values.all().delete()

        # Pop the metrics formset before super().save() —
        # ClusterForm.save() iterates self.formsets and would try to save them
        # with the Indicator as parent, but they belong to DatasetSchema.
        metrics_formset = self.formsets.pop('metrics', None)  # type: ignore[attr-defined]

        obj = super().save(commit)
        plan = self.plan
        for field_name, field in _get_category_fields(plan, Indicator, obj).items():
            field_data = self.cleaned_data.get(field_name)
            if field_data is None:
                continue
            cat_type = field.category_type
            obj.set_categories(cat_type, field_data, plan=plan)

        if commit:
            # The instance was saved already when we called `super().save()`, but things like the categories may have
            # changed afterwards without being committed.
            obj.save()

        # Save factors formset — auto-create DatasetSchema if needed
        if metrics_formset is not None and metrics_formset.is_valid():
            # Before saving, delete result metrics for factors being removed.
            # The computation cascade (operand_b FK) only deletes the computation,
            # not the target_metric, so we must clean it up explicitly.
            if obj.dataset_schema is not None:
                self._delete_result_metrics_for_removed_factors(obj.dataset_schema, metrics_formset)

            if self._has_new_factors(metrics_formset):
                schema = self._ensure_dataset_schema(obj)
                metrics_formset.instance = schema
                metrics_formset.save()
            elif obj.dataset_schema is not None:
                # Save deletions/edits even when no new factors
                metrics_formset.instance = obj.dataset_schema
                metrics_formset.save()

            # Auto-create/update computations for each factor
            if obj.dataset_schema is not None:
                self._sync_factor_computations(obj.dataset_schema, metrics_formset)

            # If all factors were removed, clean up the now-empty schema and dataset
            if obj.dataset_schema is not None and not self._has_new_factors(metrics_formset):
                self._cleanup_empty_schema(obj)

        return obj

    @staticmethod
    def _delete_result_metrics_for_removed_factors(schema: DatasetSchema, metrics_formset) -> None:
        """Delete result metrics whose factor is being removed."""
        for form in metrics_formset.forms:
            if not hasattr(form, 'cleaned_data') or not form.cleaned_data.get('DELETE'):
                continue
            factor = form.instance
            if not factor.pk:
                continue
            # Deleting the target_metric cascades to the computation too
            comps = DatasetMetricComputation.objects.filter(
                schema=schema,
                operand_a__isnull=True,
                operand_b=factor,
            ).select_related('target_metric')
            for comp in comps:
                comp.target_metric.delete()

    @staticmethod
    def _cleanup_empty_schema(indicator: Indicator) -> None:
        """Remove schema and dataset if no metrics remain after factor deletion."""
        schema = indicator.dataset_schema
        if schema is None:
            return
        if schema.metrics.exists():
            return
        # Delete associated datasets first, then the schema
        schema.datasets.all().delete()
        indicator.dataset_schema = None
        indicator.save(update_fields=['dataset_schema'])
        schema.delete()

    def _sync_factor_computations(self, schema: DatasetSchema, metrics_formset) -> None:
        """
        Auto-create/update computations for each factor.

        For each saved factor (DatasetMetric), if the user provided a result_label,
        create or update: NULL x factor = result_metric (operation=multiply).
        The factor's stored unit is compound (e.g. "tCO2e/mi"), and the result unit
        is the numerator (e.g. "tCO2e") because the indicator unit cancels out:
        indicator_unit x numerator/indicator_unit = numerator.
        """
        for form in metrics_formset.forms:
            if not hasattr(form, 'cleaned_data'):
                continue
            if form.cleaned_data.get('DELETE'):
                # Deleting a factor cascades to its computation via operand_b FK
                continue
            factor = form.instance
            if not factor.pk:
                continue
            result_label = form.cleaned_data.get('result_label', '').strip()
            if not result_label:
                # No result metric requested — clean up any existing computation
                DatasetMetricComputation.objects.filter(
                    schema=schema,
                    operand_a__isnull=True,
                    operand_b=factor,
                ).delete()
                continue

            # Result unit = numerator of factor's compound unit
            # (indicator_unit cancels: indicator_unit x numerator/indicator_unit = numerator)
            result_unit = form.cleaned_data.get('unit', '').strip()

            # Get or create the computation and target metric
            comp = (
                DatasetMetricComputation.objects
                .filter(
                    schema=schema,
                    operand_a__isnull=True,
                    operand_b=factor,
                )
                .select_related('target_metric')
                .first()
            )
            if comp:
                target = comp.target_metric
                target.label = result_label
                target.unit = result_unit
                target.save(update_fields=['label', 'unit'])
            else:
                target = DatasetMetric.objects.create(
                    schema=schema,
                    label=result_label,
                    unit=result_unit,
                )
                DatasetMetricComputation.objects.create(
                    schema=schema,
                    target_metric=target,
                    operation=DatasetMetricComputation.Operation.MULTIPLY,
                    operand_a=None,
                    operand_b=factor,
                )

    def _save_m2m(self):
        assert self.plan
        chosen_level = self.data['level']
        # Update related IndicatorLevel object, deleting it if chosen_level is empty or None
        try:
            indicator_level = IndicatorLevel.objects.get(indicator=self.instance, plan=self.plan)
            if chosen_level:
                indicator_level.level = chosen_level
                indicator_level.save()
            else:
                indicator_level.delete()
        except IndicatorLevel.DoesNotExist:
            # Indicator was not in active plan
            if chosen_level:
                IndicatorLevel.objects.create(
                    indicator=self.instance,
                    plan=self.plan,
                    level=chosen_level,
                )
        return super()._save_m2m()


class IndicatorAdminOrganizationFilter(SimpleListFilter):
    title = _('Organization')
    parameter_name = 'organization'

    def lookups(self, request: HttpRequest, model_admin):
        # Only show organizations that have indicators and are related to the current plan
        orgs_with_indicators = Indicator.objects.values_list('organization')
        plan = get_admin_cache(request).plan
        filtered_orgs = plan.related_organizations.filter(id__in=orgs_with_indicators)
        return [(org.id, org.name) for org in filtered_orgs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(organization=self.value())
        return queryset


class IndicatorCreateView(
    InitializeFormWithPlanMixin[Indicator], InitializeFormWithInitialPlanMixin[Indicator], AplansCreateView[Indicator]
):
    def get_success_url(self):
        plan = user_or_bust(self.request.user).get_active_admin_plan()
        if plan.features.enable_change_log:
            change_log_create_url = reverse('wagtailsnippets_actions_indicatorchangelogmessage:add')
            return f'{change_log_create_url}?indicator={self.instance.pk}'
        return super().get_success_url()


class IndicatorEditView(
    InitializeFormWithPlanMixin[Indicator], InitializeFormWithInitialPlanMixin[Indicator], AplansEditView[Indicator]
):
    def get_success_url(self):
        plan = user_or_bust(self.request.user).get_active_admin_plan()
        if plan.features.enable_change_log:
            change_log_create_url = reverse('wagtailsnippets_actions_indicatorchangelogmessage:add')
            return f'{change_log_create_url}?indicator={self.instance.pk}'
        return super().get_success_url()


class IndicatorIndexView(AplansIndexView[Indicator]):
    def get_queryset(self, request: HttpRequest | None = None):
        qs = super().get_queryset(request)
        qs = qs.prefetch_related('organization').prefetch_related('plans').prefetch_related('levels')
        return qs


class IndicatorEditHandler(
    BuiltInFieldCustomizationAwareEditHandlerMixin[Indicator, IndicatorForm], AplansTabbedInterface[Indicator, IndicatorForm]
):
    def get_form_class(self):
        request = ctx_request.get_admin_request()
        instance = ctx_instance.get_as_type(Indicator)
        plan = request.get_active_admin_plan()
        cat_fields = _get_category_fields(plan, Indicator, instance, with_initial=True)

        self.base_form_class = type(
            'IndicatorForm',
            (IndicatorForm,),
            {**cat_fields},
        )

        form_class = super().get_form_class()

        return form_class


class IndicatorAdmin(AplansModelAdmin[Indicator]):
    model = Indicator
    create_view_class = IndicatorCreateView
    edit_view_class = IndicatorEditView
    index_view_class = IndicatorIndexView
    menu_icon = 'kausal-indicator'
    menu_order = 3
    menu_label = _('Indicators')
    list_display = ('name', 'organization', 'unit_display', 'quantity', 'has_data')
    list_filter = (DisconnectedIndicatorFilter,)
    search_fields = ('name',)
    permission_helper_class = IndicatorPermissionHelper

    edit_handler = IndicatorEditHandler
    base_form_class = IndicatorForm

    def _get_basic_information_tab(self, instance, request) -> ObjectList:
        """Get basic information tab for edit view."""
        panels: list[Panel] = []
        plan = request.user.get_active_admin_plan()
        is_general_admin = request.user.is_general_admin_for_plan(plan)
        is_linked_to_common_indicator = bool(instance and instance.common)
        dimensions_str: str = ', '.join(instance.dimensions.values_list('dimension__name', flat=True))
        if not dimensions_str:
            dimensions_str = str(_('none'))

        # Basic panels
        indicator_settings_panels: list[Panel] = [
            CustomizableBuiltInFieldPanel('name'),
            CustomizableBuiltInFieldPanel('time_resolution'),
            CustomizableBuiltInFieldPanel('level'),
        ]
        if is_linked_to_common_indicator:
            info_text = _(
                'This indicator is linked to a common indicator, so quantity, unit and dimensions cannot be edited. '
                'Current quantity: %(quantity)s; unit: %(unit)s; dimensions: %(dimensions)s',
            ) % {
                'quantity': instance.quantity,
                'unit': instance.unit,
                'dimensions': dimensions_str,
            }
            indicator_settings_panels.insert(0, HelpPanel(f'<p class="help-block help-info">{info_text}</p>'))
        else:
            quantity_panel = FieldPanel('quantity', widget=autocomplete.ModelSelect2(url='quantity-autocomplete'))
            unit_panel = FieldPanel('unit', widget=autocomplete.ModelSelect2(url='unit-autocomplete'))
            indicator_settings_panels.insert(1, quantity_panel)
            indicator_settings_panels.insert(2, unit_panel)
            if is_general_admin:
                indicator_settings_panels.insert(4, CustomizableBuiltInFieldPanel('visibility'))
        panels.append(
            MultiFieldPanel(
                indicator_settings_panels,
                heading=_('Indicator settings'),
            ),
        )

        # Categories
        category_fields = _get_category_fields(plan, Indicator, instance, with_initial=True)
        category_panels = [FieldPanel(key, heading=field.label) for key, field in category_fields.items()]
        if category_panels:
            panels.append(MultiFieldPanel(category_panels, heading=_('Classification'), classname='collapsed'))

        # Further information
        panels.append(
            MultiFieldPanel(
                children=[
                    CustomizableBuiltInFieldPanel('description'),
                    CustomizableBuiltInFieldPanel('reference'),
                ],
                heading=_('Description'),
                classname='collapsed',
            ),
        )

        indicator_page_settings_panels = [FieldPanel('hide_indicator_graph'), FieldPanel('hide_indicator_table')]

        # Visualisation settings
        visualisation_settings_panels = [
            FieldRowPanel(
                children=[
                    CustomizableBuiltInFieldPanel('min_value'),
                    CustomizableBuiltInFieldPanel('max_value'),
                ],
            ),
            FieldRowPanel(
                children=[
                    CustomizableBuiltInFieldPanel('ticks_count'),
                    CustomizableBuiltInFieldPanel('ticks_rounding'),
                ],
            ),
            CustomizableBuiltInFieldPanel('value_rounding'),
            CustomizableBuiltInFieldPanel('show_total_line'),
            CustomizableBuiltInFieldPanel('show_trendline'),
            CustomizableBuiltInFieldPanel('desired_trend'),
            CustomizableBuiltInFieldPanel('data_categories_are_stackable'),
        ]
        panels.append(
            MultiFieldPanel(
                indicator_page_settings_panels,
                heading=_('Indicator page settings'),
                classname='collapsed',
            )
        )

        panels.append(
            MultiFieldPanel(
                visualisation_settings_panels,
                heading=_('Visualization settings'),
                classname='collapsed',
            )
        )

        # Advanced settings
        advanced_panels: list[Panel] = [
            FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        ]
        if instance and instance.pk and not instance.dimensions.exists():
            advanced_panels.append(FieldPanel('reference_value', widget=IndicatorValueChooser(indicator_id=instance.id)))

        advanced_panels.append(
            FieldPanel('sort_key'),
        )

        advanced_panels.extend([
            FieldPanel('goal_description'),
            FieldPanel('non_quantified_goal'),
            FieldPanel('non_quantified_goal_date'),
        ])

        if instance and instance.pk and plan.kausal_paths_instance_uuid:
            advanced_panels.append(FieldPanel('kausal_paths_node_uuid'))

        if not is_linked_to_common_indicator and is_general_admin:
            advanced_panels.append(
                CondensedInlinePanel(
                    'dimensions',
                    panels=[FieldPanel('dimension', widget=DimensionChooser(include_plan_dimensions=True))],
                    heading=_('Dimensions'),
                ),
            )

            # If the indicator has values, show a warning that these would be deleted by changing dimensions
            num_values = instance.values.count() if instance else 0
            if num_values:
                warning_text = ngettext_lazy(
                    'If you change the dimensions of this indicator (currently %(dimensions)s), its single value will '
                    'be deleted.',
                    'If you change the dimensions of this indicator (currently %(dimensions)s), all its %(num)d '
                    'values will be deleted.',
                    num_values,
                ) % {
                    'dimensions': dimensions_str,
                    'num': num_values,
                }
                # Actually the warning shouldn't be a separate panel for logical reasons and because it would avoid
                # the ugly gap, but it seems nontrivial to do properly.
                advanced_panels.append(HelpPanel(f'<p class="help-block help-warning">{warning_text}</p>'))

        panels.append(
            MultiFieldPanel(advanced_panels, heading=_('Advanced settings'), classname='collapsed'),
        )

        return ObjectList(panels, heading=_('Basic information'))

    def _get_contact_persons_tab(self) -> ObjectList:
        """Get contact persons tab for edit view."""
        panels: list[Panel] = [
            CondensedInlinePanel(
                'contact_persons',
                panels=[
                    FieldPanel('person', widget=PersonChooser),
                ],
            ),
        ]
        return ObjectList(panels, heading=_('Contact persons'))

    def _get_reporting_tab(self) -> ObjectList:
        """Get reporting tab for edit view."""
        panels: list[Panel] = [
            CustomizableBuiltInFieldPanel('internal_notes'),
            CustomizableBuiltInFieldPanel('updated_values_due_at'),
        ]
        return ObjectList(panels, heading=_('Reporting'))

    @staticmethod
    def _get_dataset_editor_link_panel(instance: Indicator | None) -> HelpPanel | None:
        """Return a HelpPanel with a link to the dataset editor, or None if no schema exists."""
        if instance is None or not instance.pk or instance.dataset_schema is None:
            return None
        try:
            from kausal_watch_extensions.dataset_editor import DatasetViewSet as DatasetEditorViewSet
        except ImportError:
            return None
        schema = instance.dataset_schema
        dataset = Dataset.objects.filter(schema=schema, scope_id=instance.pk).first()
        editor_vs = DatasetEditorViewSet()
        if dataset is not None:
            url = reverse(editor_vs.get_url_name('edit'), args=[dataset.pk])
            label = _('Edit factor data')
        else:
            url = reverse(editor_vs.get_url_name('add'))
            url += f'?dataset_schema_uuid={schema.uuid}&model=indicators.Indicator&object_id={instance.pk}'
            label = _('Add factor data')
        return HelpPanel(content=(f'<a href="{url}" class="button button-small button-secondary">{label}</a>'))

    def _get_relationships_tab(self, instance: Indicator | None = None) -> ObjectList:
        """Get relationships tab for edit view."""
        request = ctx_request.get()
        plan = get_admin_cache(request).plan

        actions_panels: list[Panel] = [
            InlinePanel(
                'related_actions',
                panels=[
                    CustomizableBuiltInFieldPanel(
                        'action',
                        widget=autocomplete.ModelSelect2(
                            url='action-autocomplete',
                            forward=(dal_forward.Const(val=True, dst='only_modifiable'),),
                        ),
                    ),
                    CustomizableBuiltInFieldPanel('effect_type'),
                    CustomizableBuiltInFieldPanel('indicates_action_progress'),
                ],
                heading=_('Indicator for actions'),
            ),
        ]

        other_indicators_panels = [
            InlinePanel(
                'related_effects',
                panels=[
                    FieldPanel('effect_indicator', widget=autocomplete.ModelSelect2(url='indicator-autocomplete')),
                    FieldPanel('effect_type'),
                    FieldPanel('confidence_level'),
                ],
                heading=_('Effects'),
            ),
            InlinePanel(
                'related_causes',
                panels=[
                    FieldPanel('causal_indicator', widget=autocomplete.ModelSelect2(url='indicator-autocomplete')),
                    FieldPanel('effect_type'),
                    FieldPanel('confidence_level'),
                ],
                heading=_('Causes'),
            ),
        ]

        panels: list[Panel] = [
            FieldPanel('common', widget=autocomplete.ModelSelect2(url='common-indicator-autocomplete')),
            MultiFieldPanel(actions_panels, heading=pgettext_lazy('Action model', 'Actions')),
            MultiFieldPanel(other_indicators_panels, heading=_('Other indicators')),
        ]

        if plan.features.enable_indicator_factors:
            has_dimensions = instance is not None and instance.pk and instance.dimensions.exists()
            if has_dimensions:
                factors_panels: list[Panel] = [
                    HelpPanel(content=_('Factors cannot be added to indicators that have dimensions in their data.')),
                ]
            else:
                factors_panels = [
                    HelpPanel(
                        content=_(
                            "Factors are multiplied with this indicator's values to calculate a derived output, "
                            'such as total emissions or cost. '
                            'Add factor values to the indicator data editor.'
                        )
                    ),
                    IndicatorMetricsInlinePanel(
                        'metrics',
                        panels=[
                            FieldPanel('label', heading=_('Name')),
                            FieldPanel('unit'),
                            FieldPanel('result_label'),
                        ],
                        label=_('factor'),
                    ),
                ]
                dataset_link_panel = self._get_dataset_editor_link_panel(instance)
                if dataset_link_panel is not None:
                    factors_panels.append(dataset_link_panel)
            panels.append(MultiFieldPanel(factors_panels, heading=_('Factors')))

        return ObjectList(panels, heading=_('Relationships'))

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = cast('Indicator', ctx_instance.get())  # FIXME: Fails when creating a new indicator

        tabs = [
            self._get_basic_information_tab(instance, request),
            self._get_contact_persons_tab(),
            self._get_reporting_tab(),
            self._get_relationships_tab(instance),
            *get_translation_tabs(instance, request),
        ]

        return IndicatorEditHandler(tabs)

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.is_superuser:
            list_filter += (IndicatorAdminOrganizationFilter,)

        return list_filter

    @admin.display(description=_('Unit'))
    def unit_display(self, obj):
        unit = obj.unit
        if not unit:
            return ''
        return unit.short_name or unit.name

    def get_queryset(self, request: HttpRequest):
        qs = super().get_queryset(request)
        user = user_or_bust(request.user)
        plan = get_admin_cache(request).plan
        if user.is_superuser:
            qs = qs.filter(organization__in=Organization.objects.qs.available_for_plan(plan))
        else:
            orgs = [plan.organization.id]
            orgs.extend(Organization.objects.qs.user_is_plan_admin_for(user, plan).values_list('id', flat=True))
            qs = qs.filter(organization_id__in=orgs)
        return qs.select_related('unit', 'quantity')


class CommonIndicatorForm(AplansAdminModelForm[CommonIndicator]):
    def clean(self):
        if self.instance.pk and 'dimensions' in self.formsets:
            # Dimensions cannot be accessed from self.instance.dimensions yet
            sorted_form_data = sorted(self.formsets['dimensions'].cleaned_data, key=lambda d: d.get('ORDER', 0))
            new_dimensions = [d['dimension'].id for d in sorted_form_data if not d.get('DELETE')]
            for indicator in self.instance.indicators.all():
                indicator_dimensions = list(indicator.dimensions.values_list('dimension', flat=True))
                if new_dimensions != indicator_dimensions:
                    raise ValidationError(_('Dimensions must be the same as in all indicators linked to this one'))
        return super().clean()


class CommonIndicatorAdmin(AplansModelAdmin[CommonIndicator]):
    model = CommonIndicator
    menu_icon = 'kausal-indicator'  # FIXME
    menu_label = _('Common indicators')
    list_display = ('name', 'unit_display', 'quantity')
    search_fields = ('name',)

    basic_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
        FieldPanel('description'),
    ]

    @admin.display(description=_('Unit'))
    def unit_display(self, obj):
        unit = obj.unit
        if not unit:
            return ''
        return unit.short_name or unit.name

    def get_edit_handler(self):
        instance = ctx_instance.get()  # FIXME: Fails when creating a new common indicator
        basic_panels: list[Panel[Any]] = list(self.basic_panels)

        # Some fields should only be editable if no indicator is linked to the common indicator
        if not instance.pk or not instance.indicators.exists():
            basic_panels.insert(1, FieldPanel('quantity'))
            basic_panels.insert(2, FieldPanel('unit'))
            basic_panels.append(
                CondensedInlinePanel(
                    'dimensions',
                    panels=[
                        FieldPanel('dimension'),
                    ],
                    heading=_('Dimensions'),
                )
            )
        else:
            dimensions_str: str = ', '.join(instance.dimensions.values_list('dimension__name', flat=True))
            if not dimensions_str:
                dimensions_str = str(_('none'))
            info_text = _(
                'This common indicator has indicators linked to it, so quantity, unit and dimensions cannot '
                'be edited. Current quantity: %(quantity)s; unit: %(unit)s; dimensions: %(dimensions)s'
            ) % {
                'quantity': instance.quantity,
                'unit': instance.unit,
                'dimensions': dimensions_str,
            }
            basic_panels.insert(0, HelpPanel(f'<p class="help-block help-info">{info_text}</p>'))

        handler = ObjectList[CommonIndicator, CommonIndicatorForm](basic_panels)
        handler.base_form_class = CommonIndicatorForm
        return handler


class IndicatorGroup(ModelAdminGroup):
    menu_label = _('Indicators')
    menu_icon = 'kausal-indicator'
    menu_order = 20
    items: tuple[type[AplansModelAdmin[Any]], ...] = (
        IndicatorAdmin,
        CommonIndicatorAdmin,
        DimensionAdmin,
        UnitAdmin,
        QuantityAdmin,
    )


modeladmin_register(IndicatorGroup)
