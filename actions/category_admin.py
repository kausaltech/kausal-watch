from django import forms
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from wagtail.admin.edit_handlers import (
    FieldPanel, FieldRowPanel, MultiFieldPanel, ObjectList,
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.contrib.modeladmin.helpers import ButtonHelper
from wagtail.contrib.modeladmin.menus import ModelAdminMenuItem
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.contrib.modeladmin.views import DeleteView
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailorderable.modeladmin.mixins import OrderableMixin

from .admin import CategoryTypeFilter
from .models import AttributeType, Category, CategoryAttributeRichText, CategoryType, CategoryAttributeType
from admin_site.wagtail import (
    AplansCreateView, AplansEditView, AplansModelAdmin, CondensedInlinePanel, PlanFilteredFieldPanel,
    AplansTabbedInterface, get_translation_tabs
)


def _append_category_type_query_parameter(request, url):
    category_type = request.GET.get('category_type')
    if category_type:
        assert '?' not in url
        return f'{url}?category_type={category_type}'
    return url


@modeladmin_register
class CategoryTypeAdmin(AplansModelAdmin):
    model = CategoryType
    menu_icon = 'fa-briefcase'
    menu_label = _('Category types')
    menu_order = 1100
    list_display = ('name',)
    search_fields = ('name',)
    add_to_settings_menu = True

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('hide_category_identifiers'),
        FieldPanel('select_widget'),
        MultiFieldPanel([
            FieldRowPanel([
                FieldPanel('usable_for_actions'),
                FieldPanel('editable_for_actions'),
            ]),
            FieldRowPanel([
                FieldPanel('usable_for_indicators'),
                FieldPanel('editable_for_indicators'),
            ]),
        ], heading=_('Action and indicator categorization'), classname='collapsible collapsed'),
        CondensedInlinePanel('levels', panels=[
            FieldPanel('name',),
            FieldPanel('name_plural',)
        ]),
    ]

    def get_form_fields_exclude(self, request):
        exclude = super().get_form_fields_exclude(request)
        exclude += ['plan']
        return exclude

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_edit_handler(self, instance, request):
        panels = list(self.panels)
        tabs = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return AplansTabbedInterface(tabs)


@modeladmin_register
class CategoryAttributeTypeAdmin(OrderableMixin, AplansModelAdmin):
    model = CategoryAttributeType
    menu_label = pgettext_lazy('hyphenated', 'Category attributes')
    menu_order = 1200
    list_display = ('name', 'category_type')
    add_to_settings_menu = True

    panels = [
        PlanFilteredFieldPanel('category_type'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('format'),
        CondensedInlinePanel('choice_options', panels=[
            FieldPanel('name'),
            FieldPanel('identifier'),
        ])
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(category_type__plan=plan).distinct()


def get_attribute_fields(cat_type, obj, with_initial=False):
    # Return list containing pairs (attribute_type, fields), where fields is a dict mapping a form field name to a pair
    # (field, model_field_name)
    # TODO: Partly duplicated in action_admin.py
    result = []

    if not obj or not obj.pk:
        with_initial = False

    for attribute_type in cat_type.attribute_types.all():
        if attribute_type.format == AttributeType.AttributeFormat.ORDERED_CHOICE:
            initial_choice = None
            qs = attribute_type.choice_options.all()
            if with_initial:
                c = attribute_type.choice_attributes.filter(category=obj).first()
                if c:
                    initial_choice = c.choice
            field = forms.ModelChoiceField(
                qs, label=attribute_type.name, initial=initial_choice, required=False,
            )
            form_field_name = f'attribute_type_{attribute_type.identifier}'
            result.append((attribute_type, {form_field_name: (field, 'choice')}))
        elif attribute_type.format == AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            initial_choice = None
            initial_text = None
            qs = attribute_type.choice_options.all()
            if with_initial:
                cwt = attribute_type.choice_with_text_attributes.filter(category=obj).first()
                if cwt:
                    initial_choice = cwt.choice
                    initial_text = cwt.text
            choice_field = forms.ModelChoiceField(
                qs, label=attribute_type.name, initial=initial_choice, required=False,
            )
            choice_form_field_name = f'attribute_type_{attribute_type.identifier}_choice'
            text_field = CategoryAttributeRichText._meta.get_field('text').formfield(
                initial=initial_text, required=False
            )
            text_field.panel_heading = attribute_type.name
            text_form_field_name = f'attribute_type_{attribute_type.identifier}_text'
            result.append((attribute_type, {choice_form_field_name: (choice_field, 'choice'),
                                            text_form_field_name: (text_field, 'text')}))
        elif attribute_type.format == AttributeType.AttributeFormat.RICH_TEXT:
            initial_text = None
            if with_initial:
                val_obj = attribute_type.richtext_attributes.filter(category=obj).first()
                if val_obj is not None:
                    initial_text = val_obj.text

            field = CategoryAttributeRichText._meta.get_field('text').formfield(
                initial=initial_text, required=False
            )
            form_field_name = f'attribute_type_{attribute_type.identifier}'
            result.append((attribute_type, {form_field_name: (field, 'text')}))
        elif attribute_type.format == AttributeType.AttributeFormat.NUMERIC:
            initial_value = None
            if with_initial:
                val_obj = attribute_type.numeric_value_attributes.filter(category=obj).first()
                if val_obj is not None:
                    initial_value = val_obj.value
            field = forms.FloatField(
                label=attribute_type.name, initial=initial_value, required=False,
            )
            form_field_name = f'attribute_type_{attribute_type.identifier}'
            result.append((attribute_type, {form_field_name: (field, 'value')}))
        else:
            raise Exception('Unsupported attribute type format: %s' % attribute_type.format)
    return result


class AttributeFieldPanel(FieldPanel):
    def on_form_bound(self):
        super().on_form_bound()
        attribute_fields_list = get_attribute_fields(self.instance.type, self.instance, with_initial=True)
        attribute_fields = {form_field_name: field
                            for _, fields in attribute_fields_list
                            for form_field_name, (field, _) in fields.items()}
        self.form.fields[self.field_name].initial = attribute_fields[self.field_name].initial


class CategoryAdminForm(WagtailAdminModelForm):
    def save(self, commit=True):
        obj = super().save(commit)

        # Update categories
        for attribute_type, fields in get_attribute_fields(obj.type, obj):
            vals = {}
            for form_field_name, (field, model_field_name) in fields.items():
                val = self.cleaned_data.get(form_field_name)
                vals[model_field_name] = val
            attribute_type.set_action_value(obj, vals)
        return obj


class CategoryEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        if self.instance is not None:
            attribute_fields_list = get_attribute_fields(self.instance.type, self.instance, with_initial=True)
            attribute_fields = {form_field_name: field
                                for _, fields in attribute_fields_list
                                for form_field_name, (field, _) in fields.items()}
        else:
            attribute_fields = {}

        self.base_form_class = type(
            'CategoryAdminForm',
            (CategoryAdminForm,),
            attribute_fields
        )
        return super().get_form_class()


class CategoryTypeQueryParameterMixin:
    @property
    def index_url(self):
        return _append_category_type_query_parameter(self.request, super().index_url)

    @property
    def create_url(self):
        return _append_category_type_query_parameter(self.request, super().create_url)

    @property
    def edit_url(self):
        return _append_category_type_query_parameter(self.request, super().edit_url)

    @property
    def delete_url(self):
        return _append_category_type_query_parameter(self.request, super().delete_url)


class CategoryCreateView(CategoryTypeQueryParameterMixin, AplansCreateView):
    def get_instance(self):
        """Create a category instance and set its category type to the one given in the GET or POST data."""
        instance = super().get_instance()
        category_type = self.request.GET.get('category_type')
        if category_type and not instance.pk:
            assert not hasattr(instance, 'type')
            instance.type = CategoryType.objects.get(pk=int(category_type))
            if not instance.identifier and instance.type.hide_category_identifiers:
                instance.generate_identifier()
        return instance


class CategoryEditView(CategoryTypeQueryParameterMixin, AplansEditView):
    pass


class CategoryDeleteView(CategoryTypeQueryParameterMixin, DeleteView):
    pass


class CategoryAdminButtonHelper(ButtonHelper):
    def add_button(self, *args, **kwargs):
        """
        Only show "add" button if the request contains a category type.

        Set GET parameter category_type to the type for the URL when clicking the button.
        """
        if 'category_type' in self.request.GET:
            data = super().add_button(*args, **kwargs)
            data['url'] = _append_category_type_query_parameter(self.request, data['url'])
            return data
        return None

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = _append_category_type_query_parameter(self.request, data['url'])
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = _append_category_type_query_parameter(self.request, data['url'])
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = _append_category_type_query_parameter(self.request, data['url'])
        return data


class CategoryOfSameTypePanel(PlanFilteredFieldPanel):
    """Only show categories of the same category type as the current category instance."""

    def on_form_bound(self):
        super().on_form_bound()
        field = self.bound_field.field
        field.queryset = field.queryset.filter(type=self.instance.type)


class CategoryAdminMenuItem(ModelAdminMenuItem):
    def is_shown(self, request):
        # Hide it because we will have menu items for listing categories of specific types.
        # Note that we need to register CategoryAdmin nonetheless, otherwise the URLs wouldn't be set up.
        return False


@modeladmin_register
class CategoryAdmin(OrderableMixin, AplansModelAdmin):
    menu_label = _('Categories')
    menu_order = 1300
    list_display = ('__str__', 'parent', 'type')
    list_filter = (CategoryTypeFilter,)
    model = Category
    add_to_settings_menu = True

    panels = [
        CategoryOfSameTypePanel('parent'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('short_description'),
        ImageChooserPanel('image'),
        FieldPanel('color'),
    ]

    create_view_class = CategoryCreateView
    edit_view_class = CategoryEditView
    # Do we need to create a view for inspect_view?
    delete_view_class = CategoryDeleteView
    button_helper_class = CategoryAdminButtonHelper

    def get_menu_item(self, order=None):
        return CategoryAdminMenuItem(self, order or self.get_menu_order())

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(type__plan=plan).distinct()

    def get_edit_handler(self, instance, request):
        panels = list(self.panels)
        # If the category type doesn't have semantic identifiers, we
        # hide the whole panel.
        if instance.type.hide_category_identifiers:
            for p in panels:
                if p.field_name == 'identifier':
                    panels.remove(p)
                    break

        tabs = [ObjectList(panels, heading=_('Basic information'))]

        if instance and instance.type:
            attribute_fields = get_attribute_fields(instance.type, instance, with_initial=True)
        else:
            attribute_fields = {}

        attribute_panels = []
        for attribute_type, fields in attribute_fields:
            for form_field_name, (field, model_field_name) in fields.items():
                if len(fields) > 1:
                    heading = f'{attribute_type.name} ({model_field_name})'
                else:
                    heading = attribute_type.name
                attribute_panels.append(AttributeFieldPanel(form_field_name, heading=heading))

        tabs.append(ObjectList(attribute_panels, heading=_('Attributes')))

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return CategoryEditHandler(tabs)
