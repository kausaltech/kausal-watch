from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
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
from .attribute_type_admin import get_attribute_fields
from .models import AttributeType, Category, CategoryType
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


def get_category_attribute_fields(category_type, category, **kwargs):
    category_ct = ContentType.objects.get_for_model(Category)
    category_type_ct = ContentType.objects.get_for_model(category_type)
    attribute_types = AttributeType.objects.filter(
        object_content_type=category_ct,
        scope_content_type=category_type_ct,
        scope_id=category_type.id,
    )
    return get_attribute_fields(attribute_types, category, **kwargs)


class AttributeFieldPanel(FieldPanel):
    def on_form_bound(self):
        super().on_form_bound()
        attribute_fields_list = get_category_attribute_fields(self.instance.type, self.instance, with_initial=True)
        attribute_fields = {form_field_name: field
                            for _, fields in attribute_fields_list
                            for form_field_name, (field, _) in fields.items()}
        self.form.fields[self.field_name].initial = attribute_fields[self.field_name].initial


class CategoryAdminForm(WagtailAdminModelForm):
    def clean_identifier(self):
        # Since we hide the category type in the form, `validate_unique()` will be called with `exclude` containing
        # `type`, in which case the unique_together constraints of Category will not be checked. We do it manually here.
        # Similarly, the unique_together containing `external_identifier` will not be checked, but `external_identifier`
        # is not part of the form, so no need to check.
        identifier = self.cleaned_data['identifier']
        type = self.instance.type
        if Category.objects.filter(type=type, identifier=identifier).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("There is already a category with this identifier."))
        return identifier

    def save(self, commit=True):
        obj = super().save(commit)

        # Update categories
        # TODO: Refactor duplicated code (action_admin.py)
        for attribute_type, fields in get_category_attribute_fields(obj.type, obj):
            vals = {}
            for form_field_name, (field, model_field_name) in fields.items():
                val = self.cleaned_data.get(form_field_name)
                vals[model_field_name] = val
            attribute_type.set_value(obj, vals)
        return obj


class CategoryEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        # TODO: Refactor duplicated code (action_admin.py)
        if self.instance is not None:
            attribute_fields_list = get_category_attribute_fields(self.instance.type, self.instance, with_initial=True)
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
    # TODO: duplicated as AttributeTypeAdminButtonHelper
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

        # TODO: Refactor duplicated code (action_admin.py)
        if instance:
            attribute_fields = get_category_attribute_fields(instance.type, instance, with_initial=True)
        else:
            attribute_fields = []

        for attribute_type, fields in attribute_fields:
            for form_field_name, (field, model_field_name) in fields.items():
                if len(fields) > 1:
                    heading = f'{attribute_type.name} ({model_field_name})'
                else:
                    heading = attribute_type.name
                panels.append(AttributeFieldPanel(form_field_name, heading=heading))

        tabs = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return CategoryEditHandler(tabs)
