import json

from dal import autocomplete
from django import forms
from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.urls import re_path, reverse
from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _, ngettext_lazy
from generic_chooser.views import ModelChooserViewSet
from generic_chooser.widgets import AdminChooser
from wagtail.admin.edit_handlers import FieldPanel, HelpPanel, InlinePanel, ObjectList, RichTextFieldPanel
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.options import ModelAdmin, ModelAdminGroup, modeladmin_register
from wagtail.contrib.modeladmin.views import InstanceSpecificView
from wagtail.core import hooks

from admin_site.wagtail import (
    AplansAdminModelForm, AplansButtonHelper, AplansCreateView, AplansEditView,
    AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel,
    CondensedPanelSingleSelect, InitializeFormWithPlanMixin, InitializeFormWithUserMixin, get_translation_tabs
)
from aplans.types import WatchAdminRequest
from people.chooser import PersonChooser
from users.models import User

from .admin import DisconnectedIndicatorFilter
from .api import IndicatorValueSerializer
from .models import CommonIndicator, Dimension, Indicator, IndicatorLevel, Quantity, Unit


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


class EditValuesView(InstanceSpecificView):
    template_name = 'indicators/edit_values.html'

    @cached_property
    def edit_values_url(self):
        return self.url_helper.get_action_url('edit_values', self.pk_quoted)

    def check_action_permitted(self, user):
        return self.permission_helper.user_can_edit_obj(user, self.instance)

    def make_categories(self, cats):
        return [dict(id=cat.id, name=cat.name) for cat in cats]

    def get_dimensions(self, obj):
        dims = [
            d.dimension for d in obj.dimensions.select_related('dimension').prefetch_related('dimension__categories')
        ]
        for idx, dim in enumerate(dims):
            dim.order = idx
        return dims

    def get_context_data(self, **kwargs):
        obj = self.instance
        context = super().get_context_data(**kwargs)
        dims = self.get_dimensions(obj)

        dims_out = [{
            'id': dim.id,
            'name': dim.name,
            'order': dim.order,
            'categories': self.make_categories(dim.categories.all())
        } for dim in dims]
        context['dimensions'] = json.dumps(dims_out)

        value_qs = obj.values.order_by('date').prefetch_related('categories')
        data = IndicatorValueSerializer(value_qs, many=True).data

        context['values'] = json.dumps(data)
        context['post_values_uri'] = reverse('indicator-values', kwargs=dict(pk=self.pk_quoted))

        return context


class DimensionAdmin(AplansModelAdmin):
    model = Dimension
    menu_order = 4
    menu_icon = 'fa-arrows-h'
    menu_label = _('Indicator dimensions')
    list_display = ('name',)

    panels = [
        FieldPanel('name'),
        InlinePanel('categories', panels=[FieldPanel('name')], heading=_('Categories')),
    ]


class IndicatorButtonHelper(AplansButtonHelper):
    def edit_values_button(self, pk, obj, classnames_add=None, classnames_exclude=None):
        classnames_add = classnames_add or []
        return {
            'url': self.url_helper.get_action_url('edit_values', quote(pk)),
            'label': _('Edit data'),
            'classname': self.finalise_classname(
                classnames_add=classnames_add + ['icon', 'icon-table'],
                classnames_exclude=classnames_exclude
            ),
            'title': _('Edit indicator data'),
        }

    def get_buttons_for_obj(self, obj, exclude=None, classnames_add=None,
                            classnames_exclude=None):
        buttons = super().get_buttons_for_obj(obj, exclude, classnames_add, classnames_exclude)
        ph = self.permission_helper
        pk = getattr(obj, self.opts.pk.attname)
        if exclude is None:
            exclude = []
        if ('edit_values' not in exclude and obj is not None and ph.user_can_edit_obj(self.request.user, obj)):
            edit_values_button = self.edit_values_button(
                pk, obj, classnames_add=classnames_add, classnames_exclude=classnames_exclude
            )
            if edit_values_button:
                buttons.insert(1, edit_values_button)

        return buttons


class QuantityForm(AplansAdminModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.created_by = self.user
        # Set updated_by even when creating a new instance since updated_at is also set when creating
        self.instance.updated_by = self.user


class QuantityCreateView(InitializeFormWithUserMixin, AplansCreateView):
    pass


class QuantityEditView(InitializeFormWithUserMixin, AplansEditView):
    pass


class QuantityAdmin(AplansModelAdmin):
    model = Quantity
    create_view_class = QuantityCreateView
    edit_view_class = QuantityEditView
    menu_icon = 'fa-thermometer-half'
    menu_order = 6
    menu_label = _('Quantities')
    list_display = ('name_i18n',)

    panels = [
        FieldPanel('name'),
    ]

    def get_edit_handler(self, instance: Quantity, request: WatchAdminRequest):
        tabs = [
            ObjectList(self.panels, heading=_('General')),
            *get_translation_tabs(instance, request, include_all_languages=True)
        ]
        return AplansTabbedInterface(tabs, base_form_class=QuantityForm)

    def get_queryset(self, request):
        return super().get_queryset(request).order_by('name_i18n')


class UnitForm(AplansAdminModelForm):
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        super().__init__(*args, **kwargs)
        if self.instance.pk is None:
            self.instance.created_by = self.user
        # Set updated_by even when creating a new instance since updated_at is also set when creating
        self.instance.updated_by = self.user


class UnitCreateView(InitializeFormWithUserMixin, AplansCreateView):
    pass


class UnitEditView(InitializeFormWithUserMixin, AplansEditView):
    pass


class UnitAdmin(ModelAdmin):
    model = Unit
    create_view_class = UnitCreateView
    edit_view_class = UnitEditView
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

    def get_edit_handler(self, instance, request):
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
        sorted_form_data = sorted(self.formsets['dimensions'].cleaned_data, key=lambda d: d.get('ORDER'))
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
    button_helper_class = IndicatorButtonHelper

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

    def get_edit_handler(self, instance, request):
        basic_panels = list(self.basic_panels)
        plan = request.user.get_active_admin_plan()
        dimensions_str = ', '.join(instance.dimensions.values_list('dimension__name', flat=True))
        if not dimensions_str:
            dimensions_str = _("none")

        # Some fields should only be editable if the indicator is not linked to a common indicator
        show_dimensions_section = request.user.is_general_admin_for_plan(plan)
        if not instance or not instance.common:
            basic_panels.insert(1, FieldPanel('quantity'))
            basic_panels.insert(2, FieldPanel('unit'))
            if show_dimensions_section:
                basic_panels.append(CondensedInlinePanel('dimensions', panels=[
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
                    basic_panels.append(HelpPanel(f'<p class="help-block help-warning">{warning_text}</p>'))
        else:
            info_text = _("This indicator is linked to a common indicator, so quantity, unit and dimensions cannot be "
                          "edited. Current quantity: %(quantity)s; unit: %(unit)s; dimensions: %(dimensions)s") % {
                              'quantity': instance.quantity, 'unit': instance.unit, 'dimensions': dimensions_str
                          }
            basic_panels.insert(0, HelpPanel(f'<p class="help-block help-info">{info_text}</p>'))

        if request.user.is_superuser:
            basic_panels.insert(1, FieldPanel('organization'))
            basic_panels.insert(2, FieldPanel('common'))

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
            # Superusers get all indicators from all organizations, so offer them a way to filter by organization.
            # Non-superusers users get only indicators from the organization of the currently active plan.
            # TODO: Make this into a searchable dropdown or something
            list_filter += ('organization',)
        return list_filter

    def unit_display(self, obj):
        unit = obj.unit
        if not unit:
            return ''
        return unit.short_name or unit.name
    unit_display.short_description = _('Unit')

    def edit_values_view(self, request, instance_pk):
        kwargs = {'model_admin': self, 'instance_pk': instance_pk}
        view_class = EditValuesView
        return view_class.as_view(**kwargs)(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            plan = request.user.get_active_admin_plan()
            qs = qs.filter(organization=plan.organization).distinct().select_related('unit', 'quantity')
        return qs

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        urls += (
            re_path(
                self.url_helper.get_action_url_pattern('edit_values'),
                self.edit_values_view,
                name=self.url_helper.get_action_url_name('edit_values')
            ),
        )
        return urls


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

    def get_edit_handler(self, instance, request):
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
