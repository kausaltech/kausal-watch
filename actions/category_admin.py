from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import (
    FieldPanel, FieldRowPanel, MultiFieldPanel, ObjectList,
)
from wagtail.admin.edit_handlers import InlinePanel
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.contrib.modeladmin.helpers import ButtonHelper, PermissionHelper
from wagtail.contrib.modeladmin.menus import ModelAdminMenuItem
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.contrib.modeladmin.views import DeleteView
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailorderable.modeladmin.mixins import OrderableMixin
from wagtailsvg.edit_handlers import SvgChooserPanel

from .admin import CategoryTypeFilter, CommonCategoryTypeFilter
from .models import Category, CategoryType, CommonCategory, CommonCategoryType
from admin_site.wagtail import (
    ActionListPageBlockFormMixin, AplansAdminModelForm, AplansCreateView, AplansEditView, AplansModelAdmin,
    CondensedInlinePanel, InitializeFormWithPlanMixin,  PlanFilteredFieldPanel, AplansTabbedInterface,
    get_translation_tabs
)
from aplans.utils import append_query_parameter


class CategoryTypeCreateView(InitializeFormWithPlanMixin, AplansCreateView):
    pass


class CategoryTypeEditView(InitializeFormWithPlanMixin, AplansEditView):
    pass


class CategoryTypeDeleteView(DeleteView):
    def delete_instance(self):
        # When deleting a category type which is an instantiation of a common category type, remove link from plan
        plan = self.instance.plan
        cct = self.instance.common
        plan.common_category_types.remove(cct)
        return super().delete_instance()


class CategoryTypePermissionHelper(PermissionHelper):
    def _is_admin_of_active_plan(self, user):
        active_plan = user.get_active_admin_plan()
        return user.is_general_admin_for_plan(active_plan)

    def user_can_list(self, user):
        return self._is_admin_of_active_plan(user)

    def user_can_create(self, user):
        return self._is_admin_of_active_plan(user)

    def user_can_delete_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj.plan)

    def user_can_edit_obj(self, user, obj):
        return user.is_general_admin_for_plan(obj.plan)


@modeladmin_register
class CategoryTypeAdmin(AplansModelAdmin):
    model = CategoryType
    menu_icon = 'fa-briefcase'
    menu_label = _('Category types')
    menu_order = 1100
    list_display = ('name',)
    search_fields = ('name',)
    add_to_settings_menu = True
    create_view_class = CategoryTypeCreateView
    edit_view_class = CategoryTypeEditView
    delete_view_class = CategoryTypeDeleteView
    permission_helper_class = CategoryTypePermissionHelper

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('lead_paragraph'),
        FieldPanel('help_text'),
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
        ], heading=_('Action and indicator categorization'), classname='collapsible'),
        CondensedInlinePanel('levels', panels=[
            FieldPanel('name',),
            FieldPanel('name_plural',)
        ]),
        FieldPanel('synchronize_with_pages'),
        FieldPanel('instances_editable_by'),
        FieldPanel('action_list_filter_section'),
        FieldPanel('action_detail_content_section'),
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
        if instance and instance.common:
            panels.insert(1, FieldPanel('common'))
        tabs = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return CategoryTypeEditHandler(tabs, base_form_class=CategoryTypeForm)


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
        user = self._user
        attribute_types = obj.get_editable_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.set_attributes(obj, self.cleaned_data)
        return obj


class CategoryEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        user = request.user
        if self.instance is not None:
            attribute_types = self.instance.get_editable_attribute_types(user)
            attribute_fields = {field.name: field.django_field
                                for attribute_type in attribute_types
                                for field in attribute_type.get_form_fields(self.instance)}
        else:
            attribute_fields = {}

        self.base_form_class = type(
            'CategoryAdminForm',
            (CategoryAdminForm,),
            {**attribute_fields, '_user': user}
        )
        form_class = super().get_form_class()
        if self.instance and self.instance.common:
            if 'identifier' in form_class.base_fields:
                form_class.base_fields['identifier'].disabled = True
                form_class.base_fields['identifier'].required = False
            if 'parent' in form_class.base_fields:
                # TODO: Hide "parent" field instead of disabling?
                form_class.base_fields['parent'].disabled = True
                form_class.base_fields['parent'].required = False
        return form_class


class CategoryTypeForm(ActionListPageBlockFormMixin, AplansAdminModelForm):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        super().__init__(*args, **kwargs)


class CategoryTypeEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        common_field = form_class.base_fields.get('common')
        # The field should be displayed if and only if editing an instance that has a common category type. If it is,
        # make it read-only.
        if common_field:
            common_field.disabled = True
            common_field.required = False
        return form_class


class CategoryTypeQueryParameterMixin:
    @property
    def index_url(self):
        return append_query_parameter(self.request, super().index_url, 'category_type')

    @property
    def create_url(self):
        return append_query_parameter(self.request, super().create_url, 'category_type')

    @property
    def edit_url(self):
        return append_query_parameter(self.request, super().edit_url, 'category_type')

    @property
    def delete_url(self):
        return append_query_parameter(self.request, super().delete_url, 'category_type')


class CategoryCreateView(CategoryTypeQueryParameterMixin, AplansCreateView):
    def check_action_permitted(self, user):
        category_type_param = self.request.GET.get('category_type')
        if category_type_param:
            category_type = CategoryType.objects.get(pk=int(category_type_param))
            plan = category_type.plan
            if not category_type.are_instances_editable_by(user, plan):
                return False
        return super().check_action_permitted(user)

    def get_instance(self):
        """Create a category instance and set its category type to the one given in the GET or POST data."""
        instance = super().get_instance()
        category_type_param = self.request.GET.get('category_type')
        if category_type_param and not instance.pk:
            assert not hasattr(instance, 'type')
            instance.type = CategoryType.objects.get(pk=int(category_type_param))
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
            data['url'] = append_query_parameter(self.request, data['url'], 'category_type')
            return data
        return None

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'category_type')
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'category_type')
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'category_type')
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


class CategoryPermissionHelper(PermissionHelper):
    # Does not handle instance creation because we'd need the category type for that, for which we need the request. We
    # check these permissions in CategoryCreateView.
    def user_can_edit_obj(self, user, obj):
        return obj.type.are_instances_editable_by(user, obj.type.plan) and super().user_can_edit_obj(user, obj)

    def user_can_delete_obj(self, user, obj):
        return obj.type.are_instances_editable_by(user, obj.type.plan) and super().user_can_delete_obj(user, obj)


@modeladmin_register
class CategoryAdmin(OrderableMixin, AplansModelAdmin):
    menu_label = _('Categories')
    list_display = ('__str__', 'parent', 'type')
    list_filter = (CategoryTypeFilter,)
    model = Category

    panels = [
        CategoryOfSameTypePanel('parent'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('lead_paragraph'),
        ImageChooserPanel('image'),
        FieldPanel('color'),
        FieldPanel('help_text'),
    ]

    create_view_class = CategoryCreateView
    edit_view_class = CategoryEditView
    # Do we need to create a view for inspect_view?
    delete_view_class = CategoryDeleteView
    button_helper_class = CategoryAdminButtonHelper
    permission_helper_class = CategoryPermissionHelper

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

        main_attribute_panels, i18n_attribute_panels = instance.get_attribute_panels(request.user)
        panels += main_attribute_panels

        if request.user.is_superuser:
            # Didn't use CondensedInlinePanel for the following because there is a bug:
            # When editing a CommonCategory that already has an icon, clicking "save" will yield a validation error if
            # and only if the inline instance is collapsed.
            panels.append(InlinePanel('icons', heading=_("Icons"), panels=[
                FieldPanel('language'),
                ImageChooserPanel('image'),
                SvgChooserPanel('svg'),
            ]))

        tabs = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request, extra_panels=i18n_attribute_panels)
        tabs += i18n_tabs

        return CategoryEditHandler(tabs)


class CommonCategoryTypePermissionHelper(PermissionHelper):
    def user_can_list(self, user):
        return user.is_superuser

    def user_can_create(self, user):
        return user.is_superuser

    # def user_can_inspect_obj(self, user, obj):
    #     return user.is_superuser

    def user_can_delete_obj(self, user, obj):
        return user.is_superuser

    def user_can_edit_obj(self, user, obj):
        return user.is_superuser


@modeladmin_register
class CommonCategoryTypeAdmin(AplansModelAdmin):
    model = CommonCategoryType
    menu_icon = 'fa-briefcase'
    menu_label = _('Common category types')
    menu_order = 1101
    permission_helper_class = CommonCategoryTypePermissionHelper
    list_display = ('name',)
    search_fields = ('name',)
    add_to_settings_menu = True

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('hide_category_identifiers'),
        FieldPanel('lead_paragraph'),
        FieldPanel('help_text'),
        FieldPanel('primary_language'),
        FieldPanel('select_widget'),
        FieldPanel('has_collection'),
        MultiFieldPanel([
            FieldRowPanel([
                FieldPanel('usable_for_actions'),
                FieldPanel('editable_for_actions'),
            ]),
            FieldRowPanel([
                FieldPanel('usable_for_indicators'),
                FieldPanel('editable_for_indicators'),
            ]),
        ], heading=_('Action and indicator categorization'), classname='collapsible'),
    ]

    def get_edit_handler(self, instance, request):
        panels = list(self.panels)
        tabs = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return AplansTabbedInterface(tabs)


class CommonCategoryTypeQueryParameterMixin:
    @property
    def index_url(self):
        return append_query_parameter(self.request, super().index_url, 'common_category_type')

    @property
    def create_url(self):
        return append_query_parameter(self.request, super().create_url, 'common_category_type')

    @property
    def edit_url(self):
        return append_query_parameter(self.request, super().edit_url, 'common_category_type')

    @property
    def delete_url(self):
        return append_query_parameter(self.request, super().delete_url, 'common_category_type')


class CommonCategoryCreateView(CommonCategoryTypeQueryParameterMixin, AplansCreateView):
    def get_instance(self):
        """Create a common category instance and set its type to the one given in the GET or POST data."""
        instance = super().get_instance()
        common_category_type = self.request.GET.get('common_category_type')
        if common_category_type and not instance.pk:
            assert not hasattr(instance, 'type')
            instance.type = CommonCategoryType.objects.get(pk=int(common_category_type))
            # if not instance.identifier and instance.type.hide_category_identifiers:
            #     instance.generate_identifier()
        return instance


class CommonCategoryEditView(CommonCategoryTypeQueryParameterMixin, AplansEditView):
    pass


class CommonCategoryDeleteView(CommonCategoryTypeQueryParameterMixin, DeleteView):
    pass


class CommonCategoryAdminButtonHelper(ButtonHelper):
    def add_button(self, *args, **kwargs):
        """
        Only show "add" button if the request contains a common category type.

        Set GET parameter common_category_type to the type for the URL when clicking the button.
        """
        if 'common_category_type' in self.request.GET:
            data = super().add_button(*args, **kwargs)
            data['url'] = append_query_parameter(self.request, data['url'], 'common_category_type')
            return data
        return None

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'common_category_type')
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'common_category_type')
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'common_category_type')
        return data


class CommonCategoryAdminMenuItem(ModelAdminMenuItem):
    def is_shown(self, request):
        # Hide it because we will have menu items for listing common categories of specific types.
        # Note that we need to register CommonCategoryAdmin nonetheless, otherwise the URLs wouldn't be set up.
        return False


class CommonCategoryEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        if self.instance.pk:
            form_class.base_fields['identifier'].disabled = True
            form_class.base_fields['identifier'].required = False
        return form_class


@modeladmin_register
class CommonCategoryAdmin(OrderableMixin, AplansModelAdmin):
    menu_label = _('Common categories')
    list_display = ('name', 'identifier', 'type')
    list_filter = (CommonCategoryTypeFilter,)
    model = CommonCategory

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('lead_paragraph'),
        ImageChooserPanel('image'),
        FieldPanel('color'),
        FieldPanel('help_text'),
    ]

    create_view_class = CommonCategoryCreateView
    edit_view_class = CommonCategoryEditView
    # Do we need to create a view for inspect_view?
    delete_view_class = CommonCategoryDeleteView
    button_helper_class = CommonCategoryAdminButtonHelper

    def get_menu_item(self, order=None):
        return CommonCategoryAdminMenuItem(self, order or self.get_menu_order())

    def get_edit_handler(self, instance, request):
        panels = list(self.panels)

        if request.user.is_superuser:
            # Didn't use CondensedInlinePanel for the following because there is a bug:
            # When editing a CommonCategory that already has an icon, clicking "save" will yield a validation error if
            # and only if the inline instance is collapsed.
            panels.append(InlinePanel('icons', heading=_("Icons"), panels=[
                FieldPanel('language'),
                ImageChooserPanel('image'),
                SvgChooserPanel('svg'),
            ]))

        tabs = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(
            instance,
            request,
            include_all_languages=True,
            default_language=instance.type.primary_language,
        )
        tabs += i18n_tabs

        return CommonCategoryEditHandler(tabs)
