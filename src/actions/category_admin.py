from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar, cast

from django.contrib import messages
from django.contrib.admin.utils import unquote
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import Model
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.functional import cached_property
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
from wagtail.models import Page, ReferenceIndex
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views import snippets as snippet_views

from dal import autocomplete
from wagtail_color_panel.edit_handlers import NativeColorPanel

from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_request
from aplans.utils import append_query_parameter

from actions.blocks.mixins import ActionListPageBlockFormMixin
from actions.models.plan import Plan
from admin_site.viewsets import (
    InstancePermissionCheckedMixin,
    WatchCreateView,
    WatchDeleteView,
    WatchEditView,
    WatchIndexView,
    WatchViewSet,
)
from admin_site.wagtail import (
    AplansAdminModelForm,
    AplansTabbedInterface,
    CondensedInlinePanel,
    PlanFilteredFieldPanel,
    get_dataset_listing_buttons,
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

    from users.models import User


class CategoryTypeForm(ActionListPageBlockFormMixin, AplansAdminModelForm[CategoryType]):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        self.initial_plan_id = kwargs.pop('initial_plan_id')
        super().__init__(*args, **kwargs)
        common_field = self.fields.get('common')
        # The field is only shown for a category type that has a common category type, and then read-only
        if common_field:
            common_field.disabled = True
            common_field.required = False

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


class PanelFormMixin:
    """Use the form of the panel built for the request, not the one the viewset built at startup."""

    panel: ClassVar[Panel | None]

    def get_form_class(self):
        assert self.panel is not None
        return self.panel.get_form_class()


class InitialPlanFormMixin:
    """Like `InitializeFormWithInitialPlanMixin`, for snippet views."""

    request: HttpRequest

    def dispatch(self, request, *args, **kwargs):
        if request.method == 'GET':
            request.session['initial_plan_id'] = str(user_or_bust(request.user).get_active_admin_plan().id)
        return super().dispatch(request, *args, **kwargs)  # type: ignore[misc]

    def get_form_kwargs(self):
        return {
            **super().get_form_kwargs(),  # type: ignore[misc]
            'initial_plan_id': self.request.session.get('initial_plan_id'),
        }


CATEGORY_TYPE_PANELS: list[Panel[Any]] = [
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

CATEGORY_LEVEL_PANELS = [
    FieldPanel('name'),
    FieldPanel('name_plural'),
]


def get_category_type_panel(
    request: HttpRequest, instance: CategoryType
) -> AplansTabbedInterface[CategoryType, CategoryTypeForm]:
    panels = list(CATEGORY_TYPE_PANELS)
    if instance.common:
        panels.insert(1, FieldPanel('common'))
    levels_panels = insert_model_translation_panels(CategoryLevel, CATEGORY_LEVEL_PANELS, request, instance.plan)
    panels.append(CondensedInlinePanel('levels', panels=levels_panels, heading=_('Category levels')))
    tabs: list[Panel[Any]] = [
        ObjectList(panels, heading=_('Basic information')),
        *get_translation_tabs(instance, request),
    ]
    return AplansTabbedInterface[CategoryType, CategoryTypeForm](tabs, base_form_class=CategoryTypeForm).bind_to_model(
        CategoryType
    )


class CategoryTypeCreateView(InitialPlanFormMixin, PanelFormMixin, WatchCreateView[CategoryType]):
    def get_panel(self):
        plan = user_or_bust(self.request.user).get_active_admin_plan()
        return get_category_type_panel(self.request, CategoryType(plan=plan))


class CategoryTypeEditView(InitialPlanFormMixin, PanelFormMixin, WatchEditView[CategoryType]):
    def get_panel(self):
        return get_category_type_panel(self.request, self.object)


class DeleteOwnPagesMixin[M: Model]:
    """Delete the pages generated for the object along with it, so that they don't protect it from deletion."""

    object: M

    def get_own_pages(self) -> QuerySet[Page]:
        raise NotImplementedError

    def get_usage(self):
        if super().get_usage() is None:  # type: ignore[misc]
            return None
        page_ids = [str(pk) for pk in self.get_own_pages().values_list('pk', flat=True)]
        references = ReferenceIndex.get_references_to(self.object).exclude(
            base_content_type=ContentType.objects.get_for_model(Page), object_id__in=page_ids
        )
        return references.group_by_source_object()

    def delete_action(self):
        for page in list(self.get_own_pages()):
            page.delete()
        super().delete_action()  # type: ignore[misc]


class CategoryTypeDeleteView(DeleteOwnPagesMixin[CategoryType], WatchDeleteView[CategoryType]):
    def get_own_pages(self):
        return Page.objects.filter(pk__in=self.object.category_type_pages.values('pk'))

    def delete_action(self):
        # When deleting a category type which is an instantiation of a common category type, remove link from plan
        category_type = self.object
        if category_type.common is not None:
            category_type.plan.common_category_types.remove(category_type.common)
        super().delete_action()


class CategoryTypeViewSet(WatchViewSet[CategoryType]):
    model = CategoryType
    icon = 'kausal-category'
    menu_label = _('Category types')
    menu_order = 1100
    add_to_settings_menu = True
    url_prefix = 'actions/categorytype'
    list_display = ['name']
    search_fields = ['name']
    bulk_delete_enabled = False
    add_view_class = CategoryTypeCreateView
    edit_view_class = CategoryTypeEditView
    delete_view_class = CategoryTypeDeleteView

    edit_handler = ObjectList(CATEGORY_TYPE_PANELS, base_form_class=CategoryTypeForm)

    def get_queryset(self, request: HttpRequest):
        plan = user_or_bust(request.user).get_active_admin_plan()
        return CategoryType.objects.filter(plan=plan)


register_snippet(CategoryTypeViewSet)


class CategoryAdminForm(WagtailAdminModelForm[Category]):
    _user: User

    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        super().__init__(*args, **kwargs)
        # For the parent field, only show categories of the same type
        parent_field = cast('ModelChoiceField[Category]', self.fields['parent'])
        assert parent_field.queryset is not None
        parent_field.queryset = parent_field.queryset.filter(type=self.instance.type)
        if self.instance.common:
            # TODO: Hide "parent" field instead of disabling?
            for field_name in ('identifier', 'parent'):
                if field_name in self.fields:
                    self.fields[field_name].disabled = True
                    self.fields[field_name].required = False

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


def get_category_panel(request: HttpRequest, instance: Category) -> AplansTabbedInterface[Category, CategoryAdminForm]:
    user = user_or_bust(request.user)
    plan = user.get_active_admin_plan()
    panels = list[Panel[Any]](CategoryViewSet.panels)
    # If the category type doesn't have semantic identifiers, we hide the whole panel.
    if instance.type.hide_category_identifiers:
        panels = [p for p in panels if getattr(p, 'field_name', None) != 'identifier']

    main_attribute_panels, i18n_attribute_panels = instance.get_attribute_panels(user)
    panels += main_attribute_panels

    if user.is_superuser:
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
        panels.append(FieldPanel('kausal_paths_node_uuid'))

    panels.append(
        InlinePanel(
            'indicator_relationships',
            heading=_('Indicators'),
            panels=[
                FieldPanel('indicator', widget=autocomplete.ModelSelect2(url='indicator-autocomplete')),
                FieldPanel('type', heading=_('Type')),
            ],
        )
    )

    tabs: list[Panel[Any]] = [
        ObjectList(panels, heading=_('Basic information')),
        *get_translation_tabs(instance, request, extra_panels=i18n_attribute_panels),
    ]

    attribute_fields = {
        field.name: field.django_field
        for attribute_type in instance.get_visible_attribute_types(user)
        for field in attribute_type.get_form_fields(user, plan, instance)
    }
    base_form_class = type('CategoryAdminForm', (CategoryAdminForm,), {**attribute_fields, '_user': user})
    return AplansTabbedInterface[Category, CategoryAdminForm](tabs, base_form_class=base_form_class).bind_to_model(Category)


if TYPE_CHECKING:

    class ModelAdminMixinBase[M: Model](InstanceSpecificView[M]):
        pass

else:

    class ModelAdminMixinBase[M: Model]:
        pass


# Used by the category grid editor in kausal-extensions
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


def get_category_type_from_request(request: HttpRequest) -> CategoryType | None:
    type_id = request.GET.get('category_type')
    if not type_id:
        return None
    if not type_id.isdigit():
        raise Http404
    plan = user_or_bust(request.user).get_active_admin_plan()
    return get_object_or_404(CategoryType, pk=int(type_id), plan=plan)


def get_categories_index_url(category_type: CategoryType) -> str:
    url = reverse('wagtailsnippets_actions_category:list')
    return f'{url}?category_type={category_type.pk}'


def with_category_type(request: HttpRequest, url: str | None) -> str | None:
    if url is None or '?' in url:
        return url
    return append_query_parameter(request, url, 'category_type')


def scope_category_breadcrumbs_to_type(
    items: Sequence[BreadcrumbItem], category_type: CategoryType | None
) -> Sequence[BreadcrumbItem]:
    if category_type is None:
        return items
    index_url = reverse('wagtailsnippets_actions_category:list')
    type_url = get_categories_index_url(category_type)
    result: list[BreadcrumbItem] = [{**item, 'url': type_url} if item['url'] == index_url else item for item in items]
    return result


def get_change_log_message_url(category: Category) -> str | None:
    if not category.type.plan.features.enable_change_log:
        return None
    change_log_create_url = reverse('wagtailsnippets_actions_categorychangelogmessage:add')
    return f'{change_log_create_url}?category={category.pk}'


class CategoryIndexView(WatchIndexView[Category]):
    # The menu links to one type's categories. Scoping the queryset instead of filtering keeps reordering available.
    def get_base_queryset(self):
        qs = super().get_base_queryset().select_related('type')
        category_type = get_category_type_from_request(self.request)
        if category_type is None:
            return qs
        return qs.filter(type=category_type)

    def get_add_url(self):
        # A category needs a type, which only the menu item of each category type gives
        if get_category_type_from_request(self.request) is None:
            return None
        return with_category_type(self.request, super().get_add_url())

    def get_edit_url(self, instance: Category):
        return with_category_type(self.request, super().get_edit_url(instance))

    def get_delete_url(self, instance: Category):
        return with_category_type(self.request, super().get_delete_url(instance))

    @cached_property
    def show_ordering_column(self):
        # Positions are only meaningful within one type
        return get_category_type_from_request(self.request) is not None and super().show_ordering_column

    @cached_property
    def reorder_button(self):
        # Wagtail's button would drop the type from the URL
        button = super().reorder_button
        category_type = get_category_type_from_request(self.request)
        if button is None or category_type is None:
            return None
        button.url = f'{get_categories_index_url(category_type)}&ordering={self.sort_order_field}'
        return button

    def get_list_more_buttons(self, instance: Category):
        return [*super().get_list_more_buttons(instance), *get_dataset_listing_buttons(self.request, instance)]


class CategoryCreateView(PanelFormMixin, WatchCreateView[Category]):
    def dispatch(self, request, *args, **kwargs):
        category_type = get_category_type_from_request(request)
        if category_type is None:
            raise Http404
        if not category_type.is_instance_editable_by(request.user, category_type.plan, None):
            raise PermissionDenied
        return super().dispatch(request, *args, **kwargs)

    def get_panel(self):
        return get_category_panel(self.request, Category(type=get_category_type_from_request(self.request)))

    def initialize_instance(self, request, instance):
        """Set the new category's type to the one given in the GET data."""
        super().initialize_instance(request, instance)
        category_type = get_category_type_from_request(request)
        assert category_type is not None
        instance.type = category_type
        if category_type.hide_category_identifiers:
            instance.generate_identifier()

    def get_success_url(self):
        assert self.object is not None
        change_log_message_url = get_change_log_message_url(self.object)
        if change_log_message_url is not None:
            return change_log_message_url
        if self.continue_editing_active():
            return super().get_success_url()
        return get_categories_index_url(self.object.type)

    def get_breadcrumbs_items(self):
        return scope_category_breadcrumbs_to_type(super().get_breadcrumbs_items(), get_category_type_from_request(self.request))


class CategoryEditView(InstancePermissionCheckedMixin, PanelFormMixin, WatchEditView[Category]):
    def get_panel(self):
        return get_category_panel(self.request, self.object)

    def get_success_url(self):
        change_log_message_url = get_change_log_message_url(self.object)
        if change_log_message_url is not None:
            return change_log_message_url
        if self.continue_editing_active():
            return super().get_success_url()
        return get_categories_index_url(self.object.type)

    def get_delete_url(self):
        return with_category_type(self.request, super().get_delete_url())

    def get_breadcrumbs_items(self):
        return scope_category_breadcrumbs_to_type(super().get_breadcrumbs_items(), self.object.type)


class CategoryDeleteView(DeleteOwnPagesMixin[Category], WatchDeleteView[Category]):
    def get_own_pages(self):
        return Page.objects.filter(pk__in=self.object.category_pages.values('pk'))

    def get_success_url(self):
        return get_categories_index_url(self.object.type)


class CategoryReorderView(snippet_views.ReorderView):  # type: ignore[name-defined]  # pyright: ignore[reportAttributeAccessIssue]
    def get_category(self) -> Category:
        return get_object_or_404(Category, pk=unquote(str(self.kwargs['pk'])))

    def get_queryset(self):
        # Each type numbers its categories separately
        return self.get_category().filter_siblings(super().get_queryset())

    def post(self, request, *args, **kwargs):
        category = self.get_category()
        if not self.permission_policy.user_has_permission_for_instance(request.user, 'change', category):
            raise PermissionDenied
        response = super().post(request, *args, **kwargs)
        if category.type.synchronize_with_pages:
            category.type.synchronize_pages()
        return response


class CategoryViewSet(WatchViewSet[Category]):
    model = Category
    icon = 'kausal-category'
    menu_label = _('Categories')
    # The "Categories" menu in `admin_site.wagtail_hooks` has one item per category type
    add_to_admin_menu = False
    menu_item_is_registered = True
    url_prefix = 'actions/category'
    list_display = ['__str__', 'parent', 'type']
    ordering = 'order'
    sort_order_field = 'order'
    bulk_delete_enabled = False
    index_view_class = CategoryIndexView
    add_view_class = CategoryCreateView
    edit_view_class = CategoryEditView
    delete_view_class = CategoryDeleteView
    reorder_view_class = CategoryReorderView

    panels = [
        PlanFilteredFieldPanel('parent'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('lead_paragraph'),
        FieldPanel('image'),
        NativeColorPanel('color'),
        FieldPanel('help_text'),
    ]

    def get_queryset(self, request: HttpRequest):
        plan = user_or_bust(request.user).get_active_admin_plan()
        return Category.objects.filter(type__plan=plan)


register_snippet(CategoryViewSet)


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
