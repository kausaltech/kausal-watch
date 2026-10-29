from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from django.contrib import admin, messages
from django.contrib.admin import SimpleListFilter
from django.contrib.admin.utils import unquote
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Model
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from django.utils.translation import gettext_lazy as _
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.admin.panels import (
    FieldPanel,
    FieldRowPanel,
    InlinePanel,
    MultiFieldPanel,
    ObjectList,
)
from wagtail.admin.panels.base import Panel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views import snippets as snippet_views

from dal import autocomplete
from wagtail_color_panel.edit_handlers import NativeColorPanel
from wagtail_modeladmin.helpers.permission import PermissionHelper
from wagtail_modeladmin.menus import ModelAdminMenuItem
from wagtail_modeladmin.options import modeladmin_register
from wagtail_modeladmin.views import DeleteView
from wagtailorderable.modeladmin.mixins import OrderableMixin

from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request, get_admin_cache
from aplans.utils import append_query_parameter

from actions.blocks.mixins import ActionListPageBlockFormMixin
from actions.models.plan import Plan
from admin_site.utils import admin_req
from admin_site.viewsets import WatchCreateView, WatchDeleteView, WatchEditView, WatchIndexView, WatchViewSet
from admin_site.wagtail import (
    AplansAdminModelForm,
    AplansCreateView,
    AplansEditView,
    AplansIndexView,
    AplansModelAdmin,
    AplansTabbedInterface,
    CondensedInlinePanel,
    InitializeFormWithInitialPlanMixin,
    InitializeFormWithPlanMixin,
    PlanFilteredFieldPanel,
    QueryParameterButtonHelper,
    get_dataset_buttons,
    get_translation_tabs,
    insert_model_translation_panels,
)

from .models import Category, CategoryLevel, CategoryType, CommonCategory, CommonCategoryType

if TYPE_CHECKING:
    from collections.abc import Sequence

    from django.db.models import QuerySet
    from django.forms import ModelChoiceField
    from django.http.request import HttpRequest
    from wagtail.admin.views.generic.base import BreadcrumbItem

    from wagtail_modeladmin.views import InstanceSpecificView


class CategoryTypeFilter(SimpleListFilter):
    title = _('Category type')
    parameter_name = 'category_type'

    def lookups(self, request: HttpRequest, model_admin):
        user = admin_req(request).user
        plan = user.get_active_admin_plan()
        choices = [(i.pk, i.name) for i in plan.category_types.all()]
        return choices

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(type=self.value())
        return queryset


class CategoryTypeCreateView(
    InitializeFormWithPlanMixin[CategoryType], InitializeFormWithInitialPlanMixin[CategoryType], AplansCreateView[CategoryType]
):
    pass


class CategoryTypeEditView(
    InitializeFormWithPlanMixin[CategoryType], InitializeFormWithInitialPlanMixin[CategoryType], AplansEditView[CategoryType]
):
    pass


class CategoryTypeDeleteView(DeleteView[CategoryType]):
    def delete_instance(self):
        # When deleting a category type which is an instantiation of a common category type, remove link from plan
        assert isinstance(self.instance, CategoryType)
        plan = self.instance.plan
        cct = self.instance.common
        if cct is not None:
            plan.common_category_types.remove(cct)
        for page in self.instance.category_type_pages.all():
            page.delete()
        return super().delete_instance()


class CategoryTypePermissionHelper(PermissionHelper[CategoryType]):
    def _is_admin_of_active_plan(self, user) -> bool:
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
class CategoryTypeAdmin(AplansModelAdmin[CategoryType]):
    model = CategoryType
    menu_icon = 'kausal-category'
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
        FieldPanel('admin_help_text'),
        FieldPanel('hide_category_identifiers'),
        FieldPanel('select_widget'),
        MultiFieldPanel(
            [
                FieldRowPanel([
                    FieldPanel('usable_for_actions'),
                    FieldPanel('editable_for_actions'),
                ]),
                FieldRowPanel([
                    FieldPanel('usable_for_indicators'),
                    FieldPanel('editable_for_indicators'),
                ]),
            ],
            heading=_('Action and indicator categorization'),
            classname='collapsible',
        ),
        FieldPanel('synchronize_with_pages'),
        FieldPanel('instances_editable_by'),
        FieldPanel('action_list_filter_section'),
        FieldPanel('action_detail_content_section'),
    ]

    levels_panels = [
        FieldPanel('name'),
        FieldPanel('name_plural'),
    ]

    def get_form_fields_exclude(self, request: HttpRequest):  # type: ignore[override]
        exclude = super().get_form_fields_exclude(request)  # type: ignore[call-arg]  # pyright: ignore[reportCallIssue]
        exclude += ['plan']
        return exclude

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_edit_handler(self):
        request = ctx_request.get_admin_request()
        instance = ctx_instance.get_as_type(CategoryType)
        plan = instance.plan

        panels = list[Panel[Any]](self.panels)

        if instance and instance.common:
            panels.insert(1, FieldPanel('common'))

        levels_panels = insert_model_translation_panels(CategoryLevel, self.levels_panels, request, plan)
        panels.append(
            CondensedInlinePanel('levels', panels=levels_panels, heading=_('Category levels')),
        )

        tabs: list[Panel[Any]] = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request)
        tabs += i18n_tabs

        return CategoryTypeEditHandler(tabs, base_form_class=CategoryTypeForm)


class CategoryAdminForm(WagtailAdminModelForm[Category]):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # For the parent field, only show categories of the same type
        parent_field = cast('ModelChoiceField[Category]', self.fields['parent'])
        assert parent_field.queryset is not None
        parent_field.queryset = parent_field.queryset.filter(type=self.instance.type)

    def clean_identifier(self):
        # Since we hide the category type in the form, `validate_unique()` will be called with `exclude` containing
        # `type`, in which case the unique_together constraints of Category will not be checked. We do it manually here.
        # Similarly, the unique_together containing `external_identifier` will not be checked, but `external_identifier`
        # is not part of the form, so no need to check.
        identifier = self.cleaned_data['identifier']
        type = self.instance.type
        if Category.objects.filter(type=type, identifier=identifier).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_('There is already a category with this identifier.'))
        return identifier

    def save(self, commit=True):
        obj = super().save(commit)
        user = self._user
        # If we are serializing a draft (which happens when `commit` is false), we should include all attributes, i.e.,
        # also the non-editable ones. If we are saving a model instance, we only save the editable attributes.
        # (I copied that from ActionAdminForm, where, in contrast to categories at the moment, we indeed can have
        # drafts, but who knows, maybe we'll soon have draft categories... Anyway, good to be consistent.)
        if commit:
            attribute_types = obj.get_editable_attribute_types(user)
        else:
            attribute_types = obj.get_visible_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.on_form_save(obj, self.cleaned_data, commit=commit)
        return obj


class CategoryEditHandler(AplansTabbedInterface[Category, CategoryAdminForm]):
    def get_form_class(self):
        request = ctx_request.get_admin_request()
        instance = ctx_instance.get_as_type(Category)
        user = request.user
        plan = request.get_active_admin_plan()
        if instance is not None:
            attribute_types = instance.get_visible_attribute_types(user)
            attribute_fields = {
                field.name: field.django_field
                for attribute_type in attribute_types
                for field in attribute_type.get_form_fields(user, plan, instance)
            }
        else:
            attribute_fields = {}

        self.base_form_class = type(
            'CategoryAdminForm',
            (CategoryAdminForm,),
            {**attribute_fields, '_user': user},
        )
        form_class = super().get_form_class()
        if instance and instance.common:
            if 'identifier' in form_class.base_fields:
                form_class.base_fields['identifier'].disabled = True
                form_class.base_fields['identifier'].required = False
            if 'parent' in form_class.base_fields:
                # TODO: Hide "parent" field instead of disabling?
                form_class.base_fields['parent'].disabled = True
                form_class.base_fields['parent'].required = False
        return form_class


class CategoryTypeForm(ActionListPageBlockFormMixin, AplansAdminModelForm[CategoryType]):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        self.initial_plan_id = kwargs.pop('initial_plan_id')
        super().__init__(*args, **kwargs)

    def clean_identifier(self):
        # Since plan is not a form field, `validate_unique()` will be called with `exclude` containing `plan`, in
        # which case the unique_together constraint (plan, identifier) will not be checked. We do it manually here.
        identifier = self.cleaned_data['identifier']
        plan = self.instance.plan
        if CategoryType.objects.filter(plan=plan, identifier=identifier).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_('There is already a category type with this identifier.'))
        return identifier

    def save(self, commit=True):
        obj = super().save(commit)
        initial_plan_id = self.initial_plan_id
        if initial_plan_id and str(initial_plan_id) != str(self.plan.id):
            initial_plan = Plan.objects.get(pk=initial_plan_id)
            request = ctx_request.get_admin_request()
            messages.add_message(
                request,
                messages.WARNING,
                _(
                    'While editing this category type you have switched to a different plan. '
                    'This category type was still saved with the original plan "%s".'
                )
                % initial_plan.name,
            )
            self.plan = initial_plan
            obj.plan = self.plan
            obj.save()

        return obj


class CategoryTypeEditHandler(AplansTabbedInterface[CategoryType, CategoryTypeForm]):
    def get_form_class(self):
        form_class = super().get_form_class()
        common_field = form_class.base_fields.get('common')
        # The field should be displayed if and only if editing an instance that has a common category type. If it is,
        # make it read-only.
        if common_field:
            common_field.disabled = True
            common_field.required = False
        return form_class


if TYPE_CHECKING:

    class ModelAdminMixinBase[M: Model](InstanceSpecificView[M]):
        pass

else:

    class ModelAdminMixinBase[M: Model]:
        pass


class CategoryTypeQueryParameterMixin[M: Model](ModelAdminMixinBase[M]):
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


class CategoryCreateView(CategoryTypeQueryParameterMixin[Category], AplansCreateView[Category]):
    instance: Category

    def check_action_permitted(self, user):
        category_type_param = self.request.GET.get('category_type')
        if category_type_param:
            category_type = CategoryType.objects.get(pk=int(category_type_param))
            plan = category_type.plan
            if not category_type.is_instance_editable_by(user, plan, None):
                return False
        return super().check_action_permitted(user)

    def initialize_instance(self, request):
        """Set the new category's type to the one given in the GET data."""
        assert self.instance.pk is None
        category_type_param = request.GET.get('category_type')
        if category_type_param:
            assert not hasattr(self.instance, 'type')
            self.instance.type = CategoryType.objects.get(pk=int(category_type_param))
            assert not self.instance.identifier
            if self.instance.type.hide_category_identifiers:
                self.instance.generate_identifier()

    def get_success_url(self):
        plan = self.instance.type.plan
        if plan.features.enable_change_log:
            change_log_create_url = reverse('wagtailsnippets_actions_categorychangelogmessage:add')
            return f'{change_log_create_url}?category={self.instance.pk}'
        return super().get_success_url()


class CategoryEditView(CategoryTypeQueryParameterMixin[Category], AplansEditView[Category]):
    def get_success_url(self):
        plan = self.instance.type.plan
        if plan.features.enable_change_log:
            change_log_create_url = reverse('wagtailsnippets_actions_categorychangelogmessage:add')
            return f'{change_log_create_url}?category={self.instance.pk}'
        return super().get_success_url()


class CategoryDeleteView(CategoryTypeQueryParameterMixin[Category], DeleteView[Category]):
    def delete_instance(self):
        assert self.instance is not None
        cat: Category = self.instance
        for page in list(cat.category_pages.all()):
            page.delete()
        return super().delete_instance()


class CategoryAdminButtonHelper(QueryParameterButtonHelper):
    parameter_name = 'category_type'

    def get_buttons_for_obj(self, obj: Category, exclude=None, classnames_add=None, classnames_exclude=None):
        buttons = super().get_buttons_for_obj(obj, exclude, classnames_add, classnames_exclude)
        dataset_buttons = get_dataset_buttons(self, obj, classnames_add or [], classnames_exclude)
        buttons.extend(dataset_buttons)
        return buttons


class CategoryAdminMenuItem(ModelAdminMenuItem[Category]):
    def is_shown(self, request):
        # Hide it because we will have menu items for listing categories of specific types.
        # Note that we need to register CategoryAdmin nonetheless, otherwise the URLs wouldn't be set up.
        return False


class CategoryPermissionHelper(PermissionHelper[Category]):
    # Does not handle instance creation because we'd need the category type for that, for which we need the request. We
    # check these permissions in CategoryCreateView.
    def user_can_edit_obj(self, user, obj):
        return obj.type.is_instance_editable_by(user, obj.type.plan, None) and super().user_can_edit_obj(user, obj)

    def user_can_delete_obj(self, user, obj):
        return obj.type.is_instance_editable_by(user, obj.type.plan, None) and super().user_can_delete_obj(user, obj)


class CategoryIndexView(AplansIndexView[Category]):
    def get_queryset(self, request: HttpRequest | None = None) -> None:
        qs = super().get_queryset(self.request)
        cache = get_admin_cache(self.request)
        for obj in qs:
            ct = cache.category_types_by_id.get(obj.type_id)
            if ct is not None:
                obj.type = ct
        return qs


@modeladmin_register
class CategoryAdmin(OrderableMixin, AplansModelAdmin[Category]):
    menu_label = _('Categories')
    menu_icon = 'kausal-category'
    list_display = ('__str__', 'parent', 'type')
    list_filter = (CategoryTypeFilter,)
    model = Category

    panels: list[FieldPanel[Any]] = [
        PlanFilteredFieldPanel('parent'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('lead_paragraph'),
        FieldPanel('image'),
        NativeColorPanel('color'),
        FieldPanel('help_text'),
    ]

    create_view_class = CategoryCreateView
    edit_view_class = CategoryEditView
    # Do we need to create a view for inspect_view?
    delete_view_class = CategoryDeleteView
    button_helper_class = CategoryAdminButtonHelper  # type: ignore[assignment]
    index_view_class = CategoryIndexView
    permission_helper_class = CategoryPermissionHelper

    # Fix index_order method added by OrderableMixinMetaClass because the way Wagtail handles icons has changed and
    # wagtailorderable hasn't accounted for this.
    @admin.display(ordering='order', description=_('Order'))
    def index_order(self, obj):
        return mark_safe(
            '<div class="w-orderable__item__handle button button-small button--icon handle text-replace">'
            '<svg class="icon icon-grip default" style="padding: 0px;" aria-hidden="true">'
            '<use href="#icon-grip"></use>'
            '</svg>'
            '</div>',
        )

    def get_menu_item(self, order=None):
        return CategoryAdminMenuItem(self, order or self.get_menu_order())

    def get_queryset(self, request: HttpRequest):
        qs = cast('QuerySet[Category]', super().get_queryset(request))
        cache = get_admin_cache(request)
        plan = cache.plan
        return qs.filter(type__plan=plan).distinct()

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get_as_type(Category)
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

        all_panels = cast('list[Panel[Any]]', panels)

        user = user_or_bust(request.user)
        if user.is_superuser:
            # Didn't use CondensedInlinePanel for the following because there is a bug:
            # When editing a CommonCategory that already has an icon, clicking "save" will yield a validation error if
            # and only if the inline instance is collapsed.
            all_panels.append(
                InlinePanel(
                    'icons',
                    heading=_('Icons'),
                    panels=[
                        FieldPanel('language'),
                        FieldPanel('image'),
                    ],
                )
            )
            all_panels.append(FieldPanel('kausal_paths_node_uuid'))

        all_panels.append(
            InlinePanel(
                'indicator_relationships',
                heading=_('Indicators'),
                panels=[
                    FieldPanel('indicator', widget=autocomplete.ModelSelect2(url='indicator-autocomplete')),
                    FieldPanel('type', heading=_('Type')),
                ],
            )
        )

        tabs: list[Panel[Any]] = [ObjectList(panels, heading=_('Basic information'))]

        i18n_tabs = get_translation_tabs(instance, request, extra_panels=i18n_attribute_panels)
        tabs += i18n_tabs

        return CategoryEditHandler(tabs)


class CommonCategoryTypeForm(AplansAdminModelForm[CommonCategoryType]):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        super().__init__(*args, **kwargs)


def get_common_category_type_panel(
    request: HttpRequest, instance: CommonCategoryType
) -> AplansTabbedInterface[CommonCategoryType, CommonCategoryTypeForm]:
    tabs: list[Panel[Any]] = [
        ObjectList(CommonCategoryTypeViewSet.panels, heading=_('Basic information')),
        *get_translation_tabs(instance, request),
    ]
    return AplansTabbedInterface[CommonCategoryType, CommonCategoryTypeForm](
        tabs, base_form_class=CommonCategoryTypeForm
    ).bind_to_model(CommonCategoryType)


class PanelFormMixin:
    """Use the form of the panel built for the request, not the one the viewset built at startup."""

    panel: ClassVar[Panel | None]

    def get_form_class(self):
        assert self.panel is not None
        return self.panel.get_form_class()


class CommonCategoryTypeCreateView(PanelFormMixin, WatchCreateView[CommonCategoryType]):
    def get_panel(self):
        return get_common_category_type_panel(self.request, CommonCategoryType())


class CommonCategoryTypeEditView(PanelFormMixin, WatchEditView[CommonCategoryType]):
    def get_panel(self):
        return get_common_category_type_panel(self.request, self.object)


class CommonCategoryTypeViewSet(WatchViewSet[CommonCategoryType]):
    model = CommonCategoryType
    icon = 'kausal-category'
    menu_label = _('Common category types')
    menu_order = 1101
    add_to_settings_menu = True
    url_prefix = 'actions/commoncategorytype'
    list_display = ['name']
    search_fields = ['name']
    bulk_delete_enabled = False
    add_view_class = CommonCategoryTypeCreateView
    edit_view_class = CommonCategoryTypeEditView

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('hide_category_identifiers'),
        FieldPanel('lead_paragraph'),
        FieldPanel('help_text'),
        FieldPanel('admin_help_text'),
        FieldPanel('primary_language'),
        FieldPanel('select_widget'),
        FieldPanel('has_collection'),
        MultiFieldPanel(
            [
                FieldRowPanel([
                    FieldPanel('usable_for_actions'),
                    FieldPanel('editable_for_actions'),
                ]),
                FieldRowPanel([
                    FieldPanel('usable_for_indicators'),
                    FieldPanel('editable_for_indicators'),
                ]),
            ],
            heading=_('Action and indicator categorization'),
            classname='collapsible',
        ),
    ]


register_snippet(CommonCategoryTypeViewSet)


def get_common_category_type_from_request(request: HttpRequest) -> CommonCategoryType | None:
    type_id = request.GET.get('common_category_type')
    if not type_id:
        return None
    if not type_id.isdigit():
        raise Http404
    return get_object_or_404(CommonCategoryType, pk=int(type_id))


def get_common_categories_index_url(common_category_type: CommonCategoryType) -> str:
    url = reverse('wagtailsnippets_actions_commoncategory:list')
    return f'{url}?common_category_type={common_category_type.pk}'


def scope_breadcrumbs_to_type(
    items: Sequence[BreadcrumbItem], common_category_type: CommonCategoryType | None
) -> Sequence[BreadcrumbItem]:
    if common_category_type is None:
        return items
    index_url = reverse('wagtailsnippets_actions_commoncategory:list')
    type_url = get_common_categories_index_url(common_category_type)
    result: list[BreadcrumbItem] = [{**item, 'url': type_url} if item['url'] == index_url else item for item in items]
    return result


class CommonCategoryForm(AplansAdminModelForm[CommonCategory]):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['identifier'].disabled = True
            self.fields['identifier'].required = False


def get_common_category_panel(
    request: HttpRequest, instance: CommonCategory
) -> AplansTabbedInterface[CommonCategory, CommonCategoryForm]:
    panels = list[Panel[Any]](CommonCategoryViewSet.panels)
    if user_or_bust(request.user).is_superuser:
        # Didn't use CondensedInlinePanel for the following because there is a bug:
        # When editing a CommonCategory that already has an icon, clicking "save" will yield a validation error if
        # and only if the inline instance is collapsed.
        panels.append(
            InlinePanel(
                'icons',
                heading=_('Icons'),
                panels=[
                    FieldPanel('language'),
                    FieldPanel('image'),
                ],
            )
        )
    tabs: list[Panel[Any]] = [
        ObjectList(panels, heading=_('Basic information')),
        *get_translation_tabs(instance, request, include_all_languages=True),
    ]
    return AplansTabbedInterface[CommonCategory, CommonCategoryForm](tabs, base_form_class=CommonCategoryForm).bind_to_model(
        CommonCategory
    )


class CommonCategoryIndexView(WatchIndexView[CommonCategory]):
    # The menu links to one type's categories. Scoping the queryset instead of filtering keeps reordering available.
    def get_base_queryset(self):
        qs = super().get_base_queryset()
        common_category_type = get_common_category_type_from_request(self.request)
        if common_category_type is None:
            return qs
        return qs.filter(type=common_category_type)

    def get_add_url(self):
        url = super().get_add_url()
        common_category_type = get_common_category_type_from_request(self.request)
        if url is None or common_category_type is None:
            return url
        return f'{url}?common_category_type={common_category_type.pk}'

    @cached_property
    def show_ordering_column(self):
        # Positions are only meaningful within one type
        return get_common_category_type_from_request(self.request) is not None and super().show_ordering_column

    @cached_property
    def reorder_button(self):
        # Wagtail's button would drop the type from the URL
        button = super().reorder_button
        common_category_type = get_common_category_type_from_request(self.request)
        if button is None or common_category_type is None:
            return None
        button.url = f'{get_common_categories_index_url(common_category_type)}&ordering={self.sort_order_field}'
        return button


class CommonCategoryCreateView(PanelFormMixin, WatchCreateView[CommonCategory]):
    def get_panel(self):
        instance = CommonCategory()
        common_category_type = get_common_category_type_from_request(self.request)
        if common_category_type is not None:
            instance.type = common_category_type
        return get_common_category_panel(self.request, instance)

    def initialize_instance(self, request, instance):
        """Set the new common category's type to the one given in the GET data."""
        super().initialize_instance(request, instance)
        common_category_type = get_common_category_type_from_request(request)
        if common_category_type is not None:
            instance.type = common_category_type

    @transaction.atomic()
    def save_instance(self):
        """Create category corresponding to this common category for all plans using this common category's type."""
        instance = super().save_instance()
        for plan in instance.type.plans.all():
            ct = instance.type.category_type_instances.get(plan=plan)
            instance.instantiate_for_category_type(ct)
        return instance

    def get_success_url(self):
        if self.continue_editing_active():
            return super().get_success_url()
        assert self.object is not None
        return get_common_categories_index_url(self.object.type)

    def get_breadcrumbs_items(self):
        return scope_breadcrumbs_to_type(super().get_breadcrumbs_items(), get_common_category_type_from_request(self.request))


class CommonCategoryEditView(PanelFormMixin, WatchEditView[CommonCategory]):
    def get_panel(self):
        return get_common_category_panel(self.request, self.object)

    def get_success_url(self):
        if self.continue_editing_active():
            return super().get_success_url()
        return get_common_categories_index_url(self.object.type)

    def get_breadcrumbs_items(self):
        return scope_breadcrumbs_to_type(super().get_breadcrumbs_items(), self.object.type)


class CommonCategoryDeleteView(WatchDeleteView[CommonCategory]):
    def get_success_url(self):
        return get_common_categories_index_url(self.object.type)


class CommonCategoryReorderView(snippet_views.ReorderView):  # type: ignore[name-defined]  # pyright: ignore[reportAttributeAccessIssue]
    def get_queryset(self):
        # Each type numbers its categories separately
        category = get_object_or_404(CommonCategory, pk=unquote(str(self.kwargs['pk'])))
        return category.filter_siblings(super().get_queryset())


class CommonCategoryViewSet(WatchViewSet[CommonCategory]):
    model = CommonCategory
    icon = 'kausal-category'
    menu_label = _('Common categories')
    # The "Common categories" menu in `admin_site.wagtail_hooks` has one item per type
    add_to_admin_menu = False
    menu_item_is_registered = True
    url_prefix = 'actions/commoncategory'
    list_display = ['name', 'identifier', 'type']
    ordering = 'order'
    sort_order_field = 'order'
    bulk_delete_enabled = False
    index_view_class = CommonCategoryIndexView
    add_view_class = CommonCategoryCreateView
    edit_view_class = CommonCategoryEditView
    delete_view_class = CommonCategoryDeleteView
    reorder_view_class = CommonCategoryReorderView

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('lead_paragraph'),
        FieldPanel('image'),
        NativeColorPanel('color'),
        FieldPanel('help_text'),
    ]


register_snippet(CommonCategoryViewSet)
