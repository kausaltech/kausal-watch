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

from kausal_common.datasets.models import DatasetMetric, DatasetMetricComputation, DatasetSchema, DatasetSchemaScope
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
from indicators.panels import IndicatorComputationsInlinePanel, IndicatorMetricsInlinePanel
from orgs.models import Organization

from .models import CommonIndicator, Dimension, Indicator, IndicatorLevel, Quantity, Unit

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.admin.panels.base import Panel

    import pint

    from users.models import User


MetricsFormSet = inlineformset_factory(
    DatasetSchema,
    DatasetMetric,
    fields=['label', 'unit'],
    extra=0,
    can_delete=True,
)


class ComputationForm(forms.ModelForm):
    class Meta:
        model = DatasetMetricComputation
        fields = ['operand_a', 'operation', 'operand_b', 'target_metric']

    def __init__(self, *args, schema=None, **kwargs):
        super().__init__(*args, **kwargs)
        if schema is not None:
            metrics_qs = DatasetMetric.objects.filter(schema=schema)
        else:
            metrics_qs = DatasetMetric.objects.none()
        for field_name in ('target_metric', 'operand_a', 'operand_b'):
            self.fields[field_name].queryset = metrics_qs

    def _validate_units(
        self,
        operand_a: DatasetMetric,
        operation: str,
        operand_b: DatasetMetric,
        target: DatasetMetric,
    ) -> None:
        from aplans.dataset_config import _get_unit_registry
        ureg = _get_unit_registry()

        def parse_unit(unit_str: str) -> pint.Unit:
            if not unit_str or not unit_str.strip():
                return ureg.dimensionless
            return ureg.parse_expression(unit_str).units

        try:
            unit_a = parse_unit(operand_a.unit)
            unit_b = parse_unit(operand_b.unit)
            target_unit = parse_unit(target.unit)
        except Exception:
            return

        if operation in ('multiply', 'divide'):
            expected = unit_a * unit_b if operation == 'multiply' else unit_a / unit_b
            if not expected.is_compatible_with(target_unit):
                self.add_error('target_metric', ValidationError(
                    _('Target metric unit "%(target)s" is not compatible with the expected unit "%(expected)s".'),
                    params={'target': target.unit, 'expected': str(expected)},
                    code='incompatible_unit',
                ))
        elif operation in ('add', 'subtract'):
            if not unit_a.is_compatible_with(unit_b):
                self.add_error('operand_b', ValidationError(
                    _('Cannot %(op)s incompatible units "%(a)s" and "%(b)s".'),
                    params={'op': operation, 'a': operand_a.unit, 'b': operand_b.unit},
                    code='incompatible_operands',
                ))
            elif not unit_a.is_compatible_with(target_unit):
                self.add_error('target_metric', ValidationError(
                    _('Target metric unit "%(target)s" is not compatible with operand unit "%(expected)s".'),
                    params={'target': target.unit, 'expected': operand_a.unit},
                    code='incompatible_unit',
                ))

    def clean(self):
        cleaned = super().clean()
        operand_a = cleaned.get('operand_a')
        operand_b = cleaned.get('operand_b')
        operation = cleaned.get('operation')
        target = cleaned.get('target_metric')
        if not all((operand_a, operand_b, operation, target)):
            return cleaned
        self._validate_units(operand_a, operation, operand_b, target)
        return cleaned


ComputationsFormSet = inlineformset_factory(
    DatasetSchema,
    DatasetMetricComputation,
    form=ComputationForm,
    fields=['operand_a', 'operation', 'operand_b', 'target_metric'],
    extra=0,
    can_delete=True,
)


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
        formset_kwargs: dict[str, Any] = {
            'instance': schema,
            'prefix': 'metrics',
        }
        if self.data:
            formset_kwargs['data'] = self.data
        self.formsets['metrics'] = MetricsFormSet(**formset_kwargs)

        comp_kwargs: dict[str, Any] = {
            'instance': schema,
            'prefix': 'computations',
            'form_kwargs': {'schema': schema},
        }
        if self.data:
            comp_kwargs['data'] = self.data
        self.formsets['computations'] = ComputationsFormSet(**comp_kwargs)

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
            raise ValidationError(_("Please correct the errors in the factors section."))

        if not self.formsets['computations'].is_valid():
            raise ValidationError(_("Please correct the errors in the computations section."))

        return self.cleaned_data

    @staticmethod
    def _has_new_factors(metrics_formset: MetricsFormSet) -> bool:
        """Check if the factors formset has any new (non-deleted) factors."""
        if not metrics_formset.is_valid():
            return False
        return any(form_data and not form_data.get('DELETE') for form_data in metrics_formset.cleaned_data)

    def _ensure_dataset_schema(self, indicator: Indicator) -> DatasetSchema:
        """Auto-create a DatasetSchema for the indicator if it doesn't have one."""
        if indicator.dataset_schema is not None:
            return indicator.dataset_schema

        schema = DatasetSchema.objects.create(
            name=indicator.name,
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

        # Pop the metrics and computations formsets before super().save() —
        # ClusterForm.save() iterates self.formsets and would try to save them
        # with the Indicator as parent, but they belong to DatasetSchema.
        metrics_formset = self.formsets.pop('metrics', None)
        computations_formset = self.formsets.pop('computations', None)

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
            if self._has_new_factors(metrics_formset):
                schema = self._ensure_dataset_schema(obj)
                metrics_formset.instance = schema
                metrics_formset.save()
            elif obj.dataset_schema is not None:
                # Save deletions/edits even when no new factors
                metrics_formset.instance = obj.dataset_schema
                metrics_formset.save()

        # Save computations formset
        if computations_formset is not None and computations_formset.is_valid() and obj.dataset_schema is not None:
            computations_formset.instance = obj.dataset_schema
            computations_formset.save()

        return obj

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

    def _get_relationships_tab(self) -> ObjectList:
        """Get relationships tab for edit view."""
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

        factors_panels: list[Panel] = [
            HelpPanel(content=_(
                'Factors are metrics associated with this indicator for performing calculations. '
                'Each factor becomes a column in the dataset editor. '
                'You can configure computations between factors (e.g., activity data x emission factor = emission reductions).'
            )),
            IndicatorMetricsInlinePanel(
                'metrics',
                panels=[FieldPanel('label'), FieldPanel('unit')],
                heading=_('Factors'),
                label=_('factor'),
            ),
            HelpPanel(content=_(
                'Computations define how a target factor is calculated from two other factors. '
                'Save the indicator after adding factors so they become available in the dropdowns below.'
            )),
            IndicatorComputationsInlinePanel(
                'computations',
                panels=[
                    FieldPanel('operand_a'),
                    FieldPanel('operation'),
                    FieldPanel('operand_b'),
                    FieldPanel('target_metric'),
                ],
                heading=_('Computations'),
                label=_('computation'),
            ),
        ]

        panels = [
            FieldPanel('common', widget=autocomplete.ModelSelect2(url='common-indicator-autocomplete')),
            MultiFieldPanel(actions_panels, heading=pgettext_lazy('Action model', 'Actions')),
            MultiFieldPanel(other_indicators_panels, heading=_('Other indicators')),
            MultiFieldPanel(factors_panels, heading=_('Factors')),
        ]

        return ObjectList(panels, heading=_('Relationships'))

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = cast('Indicator', ctx_instance.get())  # FIXME: Fails when creating a new indicator

        tabs = [
            self._get_basic_information_tab(instance, request),
            self._get_contact_persons_tab(),
            self._get_reporting_tab(),
            self._get_relationships_tab(),
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
