from dal import autocomplete, forward as dal_forward
from django import forms
from django.contrib.admin import SimpleListFilter
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _, ngettext_lazy
from django.utils.translation import pgettext_lazy
from generic_chooser.views import ModelChooserViewSet
from generic_chooser.widgets import AdminChooser
from wagtail.admin.edit_handlers import (
    FieldPanel, HelpPanel, InlinePanel, ObjectList, RichTextFieldPanel, MultiFieldPanel
)
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.options import ModelAdminGroup
from wagtail.core import hooks

from .admin import DisconnectedIndicatorFilter
from .models import CommonIndicator, Dimension, Indicator, IndicatorLevel, Quantity, Unit
from admin_site.wagtail import (
    AplansAdminModelForm, AplansCreateView, AplansEditView,
    AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel,
    CondensedPanelSingleSelect, InitializeFormWithPlanMixin, get_translation_tabs
)
from aplans.context_vars import ctx_instance, ctx_request
from aplans.extensions import modeladmin_register
from orgs.models import Organization
from people.chooser import PersonChooser
from users.models import User


class IndicatorPermissionHelper(PermissionHelper):
    def user_can_inspect_obj(self, user, obj) -> bool:
        if not super().user_can_inspect_obj(user, obj):
            return False

        # The user has view permission to all actions if he is either
        # a general admin for actions or a contact person for any
        # actions.
        if user.is_superuser:
            return True

        adminable_plans = user.get_adminable_plans()
        obj_plans = obj.plans.all()
        for plan in adminable_plans:
            if plan in obj_plans:
                return True

        return False

    def user_can_edit_obj(self, user: User, obj: Indicator):
        if not super().user_can_edit_obj(user, obj):
            return False
        if user.is_superuser:
            return True

        for plan in obj.get_plans_with_access():
            if user.is_general_admin_for_plan(plan):
                return True

        return (
            user.is_contact_person_for_indicator(obj) or
            user.is_organization_admin_for_indicator(obj)
        )

    def user_can_delete_obj(self, user: User, obj: Indicator):
        if not super().user_can_delete_obj(user, obj):
            return False

        obj_plans = obj.plans.all()
        admin_for_all = all([user.is_general_admin_for_plan(plan) for plan in obj_plans])
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


class QuantityChooserViewSet(ModelChooserViewSet):
    icon = 'user'
    model = Quantity
    page_title = _("Choose a quantity")
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


class DimensionAdmin(AplansModelAdmin):
    model = Dimension
    menu_order = 4
    menu_icon = 'fa-arrows-h'
    menu_label = pgettext_lazy('hyphenated', 'Indicator dimensions')
    list_display = ('name',)

    panels = [
        FieldPanel('name'),
        InlinePanel('categories', panels=[FieldPanel('name')], heading=_('Categories')),
    ]


class QuantityForm(AplansAdminModelForm):
    pass


class QuantityAdmin(AplansModelAdmin):
    model = Quantity
    menu_icon = 'fa-thermometer-half'
    menu_order = 6
    menu_label = _('Quantities')
    list_display = ('name_i18n',)

    panels = [
        FieldPanel('name'),
    ]

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()  # FIXME: Fails when creating a new quantity
        tabs = [
            ObjectList(self.panels, heading=_('General')),
            *get_translation_tabs(instance, request, include_all_languages=True)
        ]
        return AplansTabbedInterface(tabs, base_form_class=QuantityForm)

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('name_i18n')


class UnitForm(AplansAdminModelForm):
    pass


class UnitAdmin(AplansModelAdmin):
    model = Unit
    menu_icon = 'fa-eur'
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
        instance = ctx_instance.get()  # FIXME: Fails when creating a new unit
        tabs = [
            ObjectList(self.panels, heading=_('General')),
            *get_translation_tabs(instance, request, include_all_languages=True)
        ]
        return AplansTabbedInterface(tabs, base_form_class=UnitForm)


class IndicatorForm(AplansAdminModelForm):
    LEVEL_CHOICES = (('', _('[not in active plan]')),) + Indicator.LEVELS

    level = forms.ChoiceField(choices=LEVEL_CHOICES, required=False)

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
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

    def get_dimension_ids_from_formset(self):
        if 'dimensions' not in self.formsets:
            return None
        fs = self.formsets['dimensions']
        if not hasattr(fs, 'cleaned_data'):
            return None
        sorted_form_data = sorted(fs.cleaned_data, key=lambda d: d.get('ORDER'))
        return [d['dimension'].id for d in sorted_form_data if not d.get('DELETE')]

    def clean(self):
        data = super().clean()
        common = data.get('common')
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
                raise ValidationError(_("Dimensions must be the same as in common indicator"))
        return data

    def save(self, commit=True):
        if self.instance.organization_id is None:
            self.instance.organization = self.plan.organization
        old_dimensions = list(self.instance.dimensions.values_list('dimension', flat=True))
        new_dimensions = self.get_dimension_ids_from_formset()
        if new_dimensions is not None and old_dimensions != new_dimensions:
            # Hopefully the user hasn't changed the dimensions by accident because now it's bye-bye, indicator values
            self.instance.latest_value = None
            self.instance.save()
            self.instance.values.all().delete()
        return super().save(commit)

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

    def lookups(self, request, model_admin):
        # Only show organizations that have indicators and are related to the current plan
        orgs_with_indicators = Indicator.objects.values_list('organization')
        plan = request.user.get_active_admin_plan()
        filtered_orgs = plan.related_organizations.filter(id__in=orgs_with_indicators)
        return [(org.id, org.name) for org in filtered_orgs]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(organization=self.value())
        return queryset


class IndicatorCreateView(InitializeFormWithPlanMixin, AplansCreateView):
    pass


class IndicatorEditView(InitializeFormWithPlanMixin, AplansEditView):
    pass


class IndicatorAdmin(AplansModelAdmin):
    model = Indicator
    create_view_class = IndicatorCreateView
    edit_view_class = IndicatorEditView
    menu_icon = 'fa-bar-chart'
    menu_order = 3
    menu_label = _('Indicators')
    list_display = ('name', 'organization', 'unit_display', 'quantity', 'has_data',)
    list_filter = (DisconnectedIndicatorFilter,)
    search_fields = ('name',)
    permission_helper_class = IndicatorPermissionHelper

    edit_handler = AplansTabbedInterface
    base_form_class = IndicatorForm

    basic_panels = [
        FieldPanel('name'),
        FieldPanel('time_resolution'),
        FieldPanel('updated_values_due_at'),
        FieldPanel('min_value'),
        FieldPanel('max_value'),
        FieldPanel('level'),
        InlinePanel(
            'related_actions',
            panels=[
                FieldPanel('action', widget=autocomplete.ModelSelect2(url='action-autocomplete')),
                FieldPanel('effect_type'),
                FieldPanel('indicates_action_progress'),
            ],
            heading=_('Indicator for actions'),
        ),
        RichTextFieldPanel('description'),
    ]

    advanced_panels = []

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()  # FIXME: Fails when creating a new indicator
        basic_panels = list(self.basic_panels)
        advanced_panels = list(self.advanced_panels)
        plan = request.user.get_active_admin_plan()
        dimensions_str = ', '.join(instance.dimensions.values_list('dimension__name', flat=True))
        if not dimensions_str:
            dimensions_str = _("none")

        # Some fields should only be editable if the indicator is not linked to a common indicator
        show_dimensions_section = request.user.is_general_admin_for_plan(plan)
        if not instance or not instance.common:
            basic_panels.insert(
                1, FieldPanel('quantity', widget=autocomplete.ModelSelect2(url='quantity-autocomplete'))
            )
            basic_panels.insert(
                2, FieldPanel('unit', widget=autocomplete.ModelSelect2(url='unit-autocomplete'))
            )
            if show_dimensions_section:
                advanced_panels.append(CondensedInlinePanel('dimensions', panels=[
                    FieldPanel('dimension', widget=CondensedPanelSingleSelect)
                ]))
                # If the indicator has values, show a warning that these would be deleted by changing dimensions
                num_values = instance.values.count() if instance else 0
                if num_values:
                    assert instance
                    warning_text = ngettext_lazy("If you change the dimensions of this indicator (currently "
                                                 "%(dimensions)s), its single value will be deleted.",
                                                 "If you change the dimensions of this indicator (currently "
                                                 "%(dimensions)s), all its %(num)d values will be deleted.",
                                                 num_values) % {'dimensions': dimensions_str, 'num': num_values}
                    # Actually the warning shouldn't be a separate panel for logical reasons and because it would avoid
                    # the ugly gap, but it seems nontrivial to do properly.
                    advanced_panels.append(HelpPanel(f'<p class="help-block help-warning">{warning_text}</p>'))
                basic_panels.append(
                    MultiFieldPanel(
                        children=advanced_panels, heading=_('Advanced options'), classname='collapsible collapsed'
                    )
                )
        else:
            info_text = _("This indicator is linked to a common indicator, so quantity, unit and dimensions cannot be "
                          "edited. Current quantity: %(quantity)s; unit: %(unit)s; dimensions: %(dimensions)s") % {
                              'quantity': instance.quantity, 'unit': instance.unit, 'dimensions': dimensions_str
                          }
            basic_panels.insert(0, HelpPanel(f'<p class="help-block help-info">{info_text}</p>'))

        if request.user.is_superuser:
            basic_panels.insert(
                1, FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete'))
            )
            basic_panels.insert(
                2, FieldPanel('common', widget=autocomplete.ModelSelect2(url='common-indicator-autocomplete'))
            )

        # Until there is a reliable way to prevent the user from editing categories of a non-editable category type
        # while another category type is editable, we will show the edit widget only when all of the category types
        # marked as usable for indicators are also marked as editable for indicators.
        ctypes = plan.category_types
        usable_ctypes = ctypes.filter(usable_for_indicators=True)
        if usable_ctypes and set(usable_ctypes) == set(ctypes.filter(editable_for_indicators=True)):
            basic_panels.append(
                FieldPanel(
                    'categories',
                    heading=_('Categories'),
                    widget=autocomplete.ModelSelect2Multiple(
                        url='category-autocomplete',
                        forward=(
                            dal_forward.Const('indicator', 'target_type'),
                        )
                    )
                )
            )

        tabs = [
            ObjectList(basic_panels, heading=_('Basic information')),
            ObjectList([
                CondensedInlinePanel(
                    'contact_persons',
                    panels=[
                        FieldPanel('person', widget=PersonChooser),
                    ]
                )
            ], heading=_('Contact persons')),
        ]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        handler = AplansTabbedInterface(tabs)
        handler.base_form_class = IndicatorForm
        return handler

    def get_list_filter(self, request):
        list_filter = super().get_list_filter(request)
        if request.user.is_superuser:
            list_filter += (IndicatorAdminOrganizationFilter,)

        return list_filter

    def unit_display(self, obj):
        unit = obj.unit
        if not unit:
            return ''
        return unit.short_name or unit.name
    unit_display.short_description = _('Unit')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        if request.user.is_superuser:
            qs = qs.filter(organization__in=Organization.objects.available_for_plan(plan))
        else:
            qs = qs.filter(organization=plan.organization)
        return qs.select_related('unit', 'quantity')


class CommonIndicatorForm(AplansAdminModelForm):
    def clean(self):
        if self.instance and 'dimensions' in self.formsets:
            # Dimensions cannot be accessed from self.instance.dimensions yet
            sorted_form_data = sorted(self.formsets['dimensions'].cleaned_data, key=lambda d: d.get('ORDER'))
            new_dimensions = [d['dimension'].id for d in sorted_form_data if not d.get('DELETE')]
            for indicator in self.instance.indicators.all():
                indicator_dimensions = list(indicator.dimensions.values_list('dimension', flat=True))
                if new_dimensions != indicator_dimensions:
                    raise ValidationError(_("Dimensions must be the same as in all indicators linked to this one"))
        return super().clean()


class CommonIndicatorAdmin(AplansModelAdmin):
    model = CommonIndicator
    menu_icon = 'fa-object-group'
    menu_label = _('Common indicators')
    list_display = ('name', 'unit_display', 'quantity')
    search_fields = ('name',)

    basic_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
        RichTextFieldPanel('description'),
    ]

    def unit_display(self, obj):
        unit = obj.unit
        if not unit:
            return ''
        return unit.short_name or unit.name
    unit_display.short_description = _('Unit')

    def get_edit_handler(self):
        instance = ctx_instance.get()  # FIXME: Fails when creating a new common indicator
        basic_panels = list(self.basic_panels)

        # Some fields should only be editable if no indicator is linked to the common indicator
        if not instance or not instance.indicators.exists():
            basic_panels.insert(1, FieldPanel('quantity'))
            basic_panels.insert(2, FieldPanel('unit'))
            basic_panels.append(CondensedInlinePanel('dimensions', panels=[
                FieldPanel('dimension', widget=CondensedPanelSingleSelect)
            ]))
        else:
            dimensions_str = ', '.join(instance.dimensions.values_list('dimension__name', flat=True))
            if not dimensions_str:
                dimensions_str = _("none")
            info_text = _("This common indicator has indicators linked to it, so quantity, unit and dimensions cannot "
                          "be edited. Current quantity: %(quantity)s; unit: %(unit)s; dimensions: %(dimensions)s") % {
                              'quantity': instance.quantity, 'unit': instance.unit, 'dimensions': dimensions_str
                          }
            basic_panels.insert(0, HelpPanel(f'<p class="help-block help-info">{info_text}</p>'))

        handler = ObjectList(basic_panels)
        handler.base_form_class = CommonIndicatorForm
        return handler


class IndicatorGroup(ModelAdminGroup):
    menu_label = _('Indicators')
    menu_icon = 'fa-bar-chart'
    menu_order = 3
    items = (IndicatorAdmin, CommonIndicatorAdmin, DimensionAdmin, UnitAdmin, QuantityAdmin)


modeladmin_register(IndicatorGroup)
