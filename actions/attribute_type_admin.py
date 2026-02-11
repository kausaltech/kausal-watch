from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from django.contrib.admin import SimpleListFilter
from django.contrib.admin.decorators import display
from django.contrib.contenttypes.models import ContentType
from django.db.models import Q
from django.forms import ValidationError
from django.urls import reverse
from django.utils.safestring import mark_safe
from django.utils.text import capfirst
from django.utils.translation import gettext_lazy as _, ngettext_lazy
from wagtail import hooks
from wagtail.admin.menu import MenuItem
from wagtail.admin.panels import FieldPanel, ObjectList, Panel
from wagtail.models import DraftStateMixin

from loguru import logger
from wagtail_modeladmin.helpers.button import ButtonHelper
from wagtail_modeladmin.menus import ModelAdminMenuItem
from wagtail_modeladmin.options import modeladmin_register
from wagtail_modeladmin.views import DeleteView, IndexView
from wagtailorderable.modeladmin.mixins import OrderableMixin

from kausal_common.users import user_or_bust

from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import OrderedModelChildFormSet

from actions.blocks.mixins import ActionListPageBlockFormMixin
from actions.chooser import CategoryTypeChooser
from admin_site.wagtail import (
    AplansAdminModelForm,
    AplansCreateView,
    AplansEditView,
    AplansModelAdmin,
    AplansTabbedInterface,
    CondensedInlinePanel,
    InitializeFormWithPlanMixin,
    insert_model_translation_panels,
)

from .attributes import AttributeType as AttributeTypeWrapper
from .models import Action, AttributeType, AttributeTypeChoiceOption, Category, Pledge
from .models.attributes import (
    Attribute,
    AttributeCategoryChoice,
    AttributeChoice,
    AttributeChoiceWithText,
    AttributeNumericValue,
    AttributeRichText,
    AttributeText,
    ModelWithAttributes,
)

if TYPE_CHECKING:
    from django.http.request import HttpRequest

logger = logger.bind(name='actions.attribute_type_admin')


@dataclass
class ChoiceOptionUsageInfo:
    published_object_names: list[str] = field(default_factory=list)
    published_object_label: str = ''
    draft_object_names: list[str] = field(default_factory=list)
    draft_object_label: str = ''
    report_names: list[str] = field(default_factory=list)

    @property
    def published_count(self) -> int:
        return len(self.published_object_names)

    @property
    def draft_count(self) -> int:
        return len(self.draft_object_names)

    @property
    def report_count(self) -> int:
        return len(self.report_names)

    @property
    def report_label(self) -> str:
        return ngettext_lazy(
            '%(count)d report',
            '%(count)d reports',
            self.report_count,
        ) % {'count': self.report_count}

    @property
    def has_usage(self) -> bool:
        return self.published_count > 0 or self.draft_count > 0 or self.report_count > 0


def _extract_choice_pk_from_revision_value(format_key: str, value: object) -> int | None:
    """Extract the choice option PK from a serialized revision attribute value."""
    if format_key in ('ordered_choice', 'unordered_choice') and isinstance(value, int):
        return value
    if format_key == 'optional_choice' and isinstance(value, dict):
        return value.get('choice')
    return None


def _collect_drafts_per_option(
    attribute_type: AttributeType, option_pks: set[int],
) -> dict[int, list[str]]:
    """Collect names of objects with unpublished drafts referencing each choice option."""
    object_model = attribute_type.object_content_type.model_class()
    assert object_model is not None

    plan = attribute_type._get_plan()
    if plan is None:
        return {}

    draft_names: dict[int, list[str]] = defaultdict(list)
    objects_with_drafts = object_model.objects.filter(  # type: ignore[attr-defined]
        plan_id=plan.pk,
        has_unpublished_changes=True,
    ).select_related('latest_revision')

    format_key = str(attribute_type.format)
    attr_type_key = str(attribute_type.pk)

    for obj in objects_with_drafts:
        revision = obj.latest_revision
        if not revision:
            continue
        attributes = revision.content.get('attributes', {})
        value = attributes.get(format_key, {}).get(attr_type_key)
        if value is None:
            continue
        choice_pk = _extract_choice_pk_from_revision_value(format_key, value)
        if choice_pk is not None and choice_pk in option_pks:
            draft_names[choice_pk].append(str(obj))

    return draft_names


def _collect_published_per_option(
    attribute_type: AttributeType, option_pks: set[int],
) -> dict[int, list[str]]:
    """Collect names of published objects referencing each choice option."""
    object_model = attribute_type.object_content_type.model_class()
    assert object_model is not None
    obj_ct = attribute_type.object_content_type

    published_names: dict[int, list[str]] = defaultdict(list)
    choice_to_obj_ids: dict[int, list[int]] = defaultdict(list)

    for choice_id, obj_id in AttributeChoice.objects.filter(
        type=attribute_type,
        content_type=obj_ct,
        choice_id__in=option_pks,
    ).values_list('choice_id', 'object_id'):
        choice_to_obj_ids[choice_id].append(obj_id)

    for choice_id, obj_id in AttributeChoiceWithText.objects.filter(
        type=attribute_type,
        content_type=obj_ct,
        choice_id__in=option_pks,
    ).values_list('choice_id', 'object_id'):
        choice_to_obj_ids[choice_id].append(obj_id)

    all_obj_ids = [oid for ids in choice_to_obj_ids.values() for oid in ids]

    if all_obj_ids:
        objects_by_id = {
            obj.id: str(obj)
            for obj in object_model.objects.filter(id__in=all_obj_ids)  # type: ignore[attr-defined]
        }

        for choice_id, obj_ids in choice_to_obj_ids.items():
            published_names[choice_id] = [
                objects_by_id[oid]
                for oid in obj_ids
                if oid in objects_by_id
            ]

    return published_names


def _get_choice_option_usage(attribute_type: AttributeType) -> dict[int, ChoiceOptionUsageInfo]:
    """
    Compute usage info for all choice options of an attribute type.

    Returns a mapping from choice_option_pk to ChoiceOptionUsageInfo.
    """
    object_model = attribute_type.object_content_type.model_class()
    assert object_model is not None
    assert issubclass(object_model, ModelWithAttributes)

    option_pks = set(attribute_type.choice_options.values_list('pk', flat=True))
    if not option_pks:
        return {}

    published_names_by_option = _collect_published_per_option(attribute_type, option_pks)

    draft_names_by_option: dict[int, list[str]] = {}
    if issubclass(object_model, DraftStateMixin):
        draft_names_by_option = _collect_drafts_per_option(attribute_type, option_pks)

    # Reports only track action attributes; for other models, skip report collection.
    used_option_pks: set[int] = set()
    report_names: list[str] = []
    if object_model is Action:
        obj_ct = attribute_type.object_content_type
        used_option_pks.update(
            AttributeChoice.objects.filter(
                type=attribute_type, content_type=obj_ct,
            ).values_list('choice_id', flat=True),
        )
        used_option_pks.update(
            AttributeChoiceWithText.objects.filter(
                type=attribute_type, content_type=obj_ct, choice_id__isnull=False,
            ).values_list('choice_id', flat=True),
        )
        used_option_pks &= option_pks

        if used_option_pks:
            from reports.models import Report
            report_names = [
                str(r) for r in Report.objects.filter(
                    is_complete=False, type__plan_id=attribute_type.scope_id,
                )
            ]

    # Build result
    result: dict[int, ChoiceOptionUsageInfo] = {}
    for pk in option_pks:
        pub_names = published_names_by_option.get(pk, [])
        draft_names = draft_names_by_option.get(pk, [])
        info = ChoiceOptionUsageInfo(
            published_object_names=pub_names,
            published_object_label=_published_label(object_model, len(pub_names)) if pub_names else '',
            draft_object_names=draft_names,
            draft_object_label=_draft_label(object_model, len(draft_names)) if draft_names else '',
            report_names=report_names if pk in used_option_pks else [],
        )
        if info.has_usage:
            result[pk] = info
    return result


ATTRIBUTE_VALUE_MODELS = [
    AttributeChoice, AttributeChoiceWithText, AttributeText,
    AttributeRichText, AttributeNumericValue, AttributeCategoryChoice,
]
_ATTRIBUTE_VALUE_MODELS_IGNORED: list[type[Attribute]] = []


def check_attribute_value_models() -> None:
    expected = {
        cls for cls in Attribute.__subclasses__()
        if not cls._meta.abstract and cls not in _ATTRIBUTE_VALUE_MODELS_IGNORED
    }
    actual = set(ATTRIBUTE_VALUE_MODELS)
    missing = expected - actual
    extra = actual - expected
    if missing:
        logger.warning('ATTRIBUTE_VALUE_MODELS is missing subclasses of Attribute: {cls}', cls=missing)
    if extra:
        logger.warning('ATTRIBUTE_VALUE_MODELS contains classes that are not subclasses of Attribute: {cls}', cls=extra)


@dataclass
class AttributeTypeUsageInfo:
    """Usage information for an AttributeType across published objects and drafts."""

    published_object_names: list[str] = field(default_factory=list)
    draft_object_names: list[str] = field(default_factory=list)
    report_names: list[str] = field(default_factory=list)
    published_label: str = ''
    draft_label: str = ''

    @property
    def published_count(self) -> int:
        return len(self.published_object_names)

    @property
    def draft_count(self) -> int:
        return len(self.draft_object_names)

    @property
    def report_count(self) -> int:
        return len(self.report_names)

    @property
    def report_label(self) -> str:
        return ngettext_lazy(
            '%(count)d report',
            '%(count)d reports',
            self.report_count,
        ) % {'count': self.report_count}

    @property
    def has_usage(self) -> bool:
        return self.published_count > 0 or self.draft_count > 0 or self.report_count > 0


def _collect_published_for_attribute_type(attribute_type: AttributeType) -> list[str]:
    """Collect names of published objects that have attribute values for this type."""
    object_model = attribute_type.object_content_type.model_class()
    assert object_model is not None

    object_ids: set[int] = set()
    for model in ATTRIBUTE_VALUE_MODELS:
        object_ids.update(
            model.objects.filter(type=attribute_type).values_list('object_id', flat=True),  # type: ignore[attr-defined]
        )

    if not object_ids:
        return []

    return sorted(str(obj) for obj in object_model.objects.filter(id__in=object_ids))  # type: ignore[attr-defined]


def _collect_drafts_for_attribute_type(attribute_type: AttributeType) -> list[str]:
    """Collect names of objects with unpublished draft attribute values for this type."""
    object_model = attribute_type.object_content_type.model_class()
    assert object_model is not None

    if not issubclass(object_model, DraftStateMixin):
        return []

    plan = attribute_type._get_plan()
    if plan is None:
        return []

    # Scope to the plan so we don't load drafts from every plan in the system.
    # This assumes every DraftStateMixin model has a plan_id field; if a future
    # model breaks that assumption, this will fail with a FieldError.
    objects_with_drafts = object_model.objects.filter(  # type: ignore[attr-defined]
        plan_id=plan.pk,
        has_unpublished_changes=True,
    ).select_related('latest_revision')

    format_key = str(attribute_type.format)
    attr_type_key = str(attribute_type.pk)

    draft_names = []
    for obj in objects_with_drafts:
        revision = obj.latest_revision
        if not revision:
            continue
        attributes = revision.content.get('attributes', {})
        value = attributes.get(format_key, {}).get(attr_type_key)
        if value is not None:
            draft_names.append(str(obj))

    return sorted(draft_names)


def _published_label(model: type[ModelWithAttributes], count: int) -> str:
    """Return a translatable label for the number of published objects of a given model."""
    if model is Action:
        label = ngettext_lazy(
            '%(count)d published action',
            '%(count)d published actions',
            count,
        )
    elif model is Category:
        label = ngettext_lazy(
            '%(count)d category',
            '%(count)d categories',
            count,
        )
    elif model is Pledge:
        label = ngettext_lazy(
            '%(count)d pledge',
            '%(count)d pledges',
            count,
        )
    else:
        # So far the models above are the only ones that support attributes. Here we catch the issue of forgetting to
        # update this function if at some point we create a new model that supports attributes.
        raise TypeError(f'Unexpected model: {model}')
    return label % {'count': count}


def _draft_label(model: type[ModelWithAttributes], count: int) -> str:
    """Return a translatable label for the number of unpublished draft objects of a given model."""
    if model is Action:
        label = ngettext_lazy(
            '%(count)d action draft',
            '%(count)d action drafts',
            count,
        )
    else:
        # So far the models above are the only ones that support attributes and drafts. Here we catch the issue of
        # forgetting to update this function if at some point we create a new model that supports attributes and drafts.
        raise TypeError(f'Unexpected model: {model}')
    return label % {'count': count}


def _collect_reports_for_attribute_type(attribute_type: AttributeType) -> list[str]:
    """Collect names of incomplete reports affected by this attribute type."""
    if attribute_type.object_content_type.model != 'action':
        return []

    from reports.models import Report
    return [
        str(r) for r in Report.objects.filter(
            is_complete=False, type__plan_id=attribute_type.scope_id,
        )
    ]


def _get_attribute_type_usage(attribute_type: AttributeType) -> AttributeTypeUsageInfo:
    """Compute usage info for an AttributeType across published objects and drafts."""
    published = _collect_published_for_attribute_type(attribute_type)
    drafts = _collect_drafts_for_attribute_type(attribute_type)

    object_model = attribute_type.object_content_type.model_class()
    assert object_model is not None
    assert issubclass(object_model, ModelWithAttributes)

    report_names = _collect_reports_for_attribute_type(attribute_type) if published else []

    extra_kwargs: dict[str, str] = {}
    if issubclass(object_model, DraftStateMixin):
        extra_kwargs['draft_label'] = _draft_label(object_model, len(drafts))

    return AttributeTypeUsageInfo(
        published_object_names=published,
        draft_object_names=drafts,
        report_names=report_names,
        published_label=_published_label(object_model, len(published)),
        **extra_kwargs,
    )


class ChoiceOptionUsagePanel(Panel):
    """Panel that warns admins about choice option usage in drafts and reports."""

    def __init__(self, usage_by_option: dict[int, ChoiceOptionUsageInfo], **kwargs):
        super().__init__(**kwargs)
        self.usage_by_option = usage_by_option

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        kwargs['usage_by_option'] = self.usage_by_option
        return kwargs

    class BoundPanel(Panel.BoundPanel):
        template_name = 'aplans/panels/choice_option_usage_panel.html'

        def __init__(self, **kwargs):
            super().__init__(**kwargs)
            option = self.instance
            if option and option.pk:
                info = self.panel.usage_by_option.get(option.pk)
            else:
                info = None

            if info is not None:
                self.published_count = info.published_count
                self.draft_count = info.draft_count
                self.report_count = info.report_count
                self.published_object_names = info.published_object_names
                self.published_object_label = info.published_object_label
                self.draft_object_names = info.draft_object_names
                self.draft_object_label = info.draft_object_label
                self.report_names = info.report_names
                self.report_label = info.report_label
                self.has_usage = info.has_usage
            else:
                self.published_count = 0
                self.draft_count = 0
                self.report_count = 0
                self.published_object_names = []
                self.published_object_label = ''
                self.draft_object_names = []
                self.draft_object_label = ''
                self.report_names = []
                self.report_label = ''
                self.has_usage = False

        def is_shown(self):
            return self.has_usage


class AttributeTypeFilter(SimpleListFilter):
    title = _('Object type')
    parameter_name = 'content_type'

    def lookups(self, request, model_admin):
        action_ct_id = ContentType.objects.get_for_model(Action).id
        category_ct_id = ContentType.objects.get_for_model(Category).id
        result = [
            (action_ct_id, Action._meta.verbose_name),
            (category_ct_id, Category._meta.verbose_name),
        ]
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        if plan.features.enable_community_engagement:
            pledge_ct_id = ContentType.objects.get_for_model(Pledge).id
            result.append((pledge_ct_id, Pledge._meta.verbose_name))
        return result

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(object_content_type_id=self.value())
        return queryset


def _append_content_type_query_parameter(request, url):
    content_type = request.GET.get('content_type')
    if content_type:
        assert '?' not in url
        return f'{url}?content_type={content_type}'
    return url


class ContentTypeQueryParameterMixin:
    request: HttpRequest

    @property
    def index_url(self):
        return _append_content_type_query_parameter(self.request, super().index_url)

    @property
    def create_url(self):
        return _append_content_type_query_parameter(self.request, super().create_url)

    @property
    def edit_url(self):
        return _append_content_type_query_parameter(self.request, super().edit_url)

    @property
    def delete_url(self):
        return _append_content_type_query_parameter(self.request, super().delete_url)


class AttributeTypeIndexView(IndexView):
    page_title = _("Fields")


class AttributeTypeCreateView(
    ContentTypeQueryParameterMixin,
    InitializeFormWithPlanMixin,
    AplansCreateView,
):
    def get_object_content_type(self):
        object_ct_id = self.request.GET.get('content_type')
        if not object_ct_id:
            return None
        return ContentType.objects.get(pk=int(object_ct_id))

    def get_page_subtitle(self):
        content_type = self.get_object_content_type()
        assert content_type is not None
        model_name = content_type.model_class()._meta.verbose_name_plural
        return _("Field for %s") % model_name

    def get_instance(self):
        """Create an attribute type instance and set its object content type to the one given in GET or POST data."""
        instance = super().get_instance()
        object_ct = self.get_object_content_type()
        if object_ct is not None and not instance.pk:
            assert not hasattr(instance, 'object_content_type')
            assert not hasattr(instance, 'scope_content_type')
            instance.object_content_type = object_ct
            if (object_ct.app_label, object_ct.model) == ('actions', 'action'):
                scope_ct_model = 'plan'
            elif (object_ct.app_label, object_ct.model) == ('actions', 'category'):
                scope_ct_model = 'categorytype'
            elif (object_ct.app_label, object_ct.model) == ('actions', 'pledge'):
                scope_ct_model = 'plan'
            else:
                raise Exception(f"Invalid content type {object_ct.app_label}.{object_ct.model}")
            instance.scope_content_type = ContentType.objects.get(app_label='actions', model=scope_ct_model)

        # If the instance is plan-specific, set plan to the active one just like we do in AplansCreateView for
        # PlanRelatedModel instances. AttributeType cannot be a PlanRelatedModel because not all attribute types are
        # plan-related.
        if instance.scope_content_type.model == 'plan' and not instance.pk:
            instance.scope_id = self.request.user.get_active_admin_plan().pk

        return instance


class AttributeTypeEditView(
    ContentTypeQueryParameterMixin,
    InitializeFormWithPlanMixin,
    AplansEditView,
):
    pass


class AttributeTypeDeleteView(ContentTypeQueryParameterMixin, DeleteView):
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['usage_info'] = _get_attribute_type_usage(self.instance)
        return context

    def get_template_names(self):
        return ['aplans/attribute_type_delete.html']


class AttributeTypeAdminButtonHelper(ButtonHelper):
    # TODO: duplicated as CategoryAdminButtonHelper
    def add_button(self, *args, **kwargs):
        """
        Only show "add" button if the request contains a content type.

        Set GET parameter content_type to the type for the URL when clicking the button.
        """
        if 'content_type' in self.request.GET:
            data = super().add_button(*args, **kwargs)
            data['url'] = _append_content_type_query_parameter(self.request, data['url'])
            return data
        return None

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = _append_content_type_query_parameter(self.request, data['url'])
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = _append_content_type_query_parameter(self.request, data['url'])
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = _append_content_type_query_parameter(self.request, data['url'])
        return data


class AttributeTypeAdminMenuItem(ModelAdminMenuItem):
    def is_shown(self, request):
        # Hide it because we will have menu items for listing attribute types of specific content types.
        # Note that we need to register AttributeTypeAdmin nonetheless, otherwise the URLs wouldn't be set up.
        return False


class AttributeTypeMenuItem(MenuItem):
    def __init__(self, content_type, **kwargs):
        self.content_type = content_type
        self.base_url = reverse('actions_attributetype_modeladmin_index')
        url = f'{self.base_url}?content_type={content_type.id}'
        model_name = capfirst(content_type.model_class()._meta.verbose_name)
        label = _("Fields (%(model)s)") % {'model': model_name}
        super().__init__(label, url, **kwargs)

    def is_active(self, request):
        path, _ = self.url.split('?', maxsplit=1)
        content_type = request.GET.get('content_type')
        return request.path.startswith(self.base_url) and content_type == str(self.content_type.pk)


@hooks.register('construct_settings_menu')
def add_attribute_types_to_settings_menu(request, items: list):
    user = request.user
    plan = user.get_active_admin_plan()
    if user.is_general_admin_for_plan(plan):
        action_ct = ContentType.objects.get_for_model(Action)
        category_ct = ContentType.objects.get_for_model(Category)
        items.append(AttributeTypeMenuItem(action_ct, icon_name='kausal-attribute'))
        items.append(AttributeTypeMenuItem(category_ct, icon_name='kausal-attribute'))

        # Only show pledge attribute types if community engagement is enabled
        if plan.features.enable_community_engagement:
            pledge_ct = ContentType.objects.get_for_model(Pledge)
            items.append(AttributeTypeMenuItem(pledge_ct, icon_name='kausal-attribute'))


class AttributeTypeForm(AplansAdminModelForm):
    def __init__(self, *args, **kwargs):
        self.plan = kwargs.pop('plan')
        super().__init__(*args, **kwargs)

    def clean_attribute_category_type(self):
        attribute_category_type = self.cleaned_data['attribute_category_type']
        format = self.cleaned_data.get('format')  # avoid blowing up if None (will fail validation elsewhere)
        if format == AttributeType.AttributeFormat.CATEGORY_CHOICE and attribute_category_type is None:
            raise ValidationError(_("If format is 'Category', a category type must be set"))
        return attribute_category_type

    def clean_unit(self):
        unit = self.cleaned_data['unit']
        format = self.cleaned_data.get('format')  # avoid blowing up if None (will fail validation elsewhere)
        if format == AttributeType.AttributeFormat.NUMERIC and unit is None:
            raise ValidationError(_("If format is 'Numeric', a unit must be set"))
        return unit


class ActionAttributeTypeForm(ActionListPageBlockFormMixin, AttributeTypeForm):
    pass


class AttributeTypeEditHandler(AplansTabbedInterface):
    def get_form_options(self):
        options = super().get_form_options()
        options['formsets']['choice_options']['formset'] = OrderedModelChildFormSet
        return options


@modeladmin_register
class AttributeTypeAdmin(OrderableMixin, AplansModelAdmin):
    model = AttributeType
    menu_icon = 'kausal-attribute'
    menu_label = _("Fields")
    menu_order = 510
    list_display = ('name', 'format')
    list_filter = (AttributeTypeFilter,)

    choice_option_panels = [
        FieldPanel('name'),
    ]

    index_view_class = AttributeTypeIndexView
    create_view_class = AttributeTypeCreateView
    edit_view_class = AttributeTypeEditView
    delete_view_class = AttributeTypeDeleteView
    button_helper_class = AttributeTypeAdminButtonHelper

    # Fix index_order method added by OrderableMixinMetaClass because the way Wagtail handles icons has changed and
    # wagtailorderable hasn't accounted for this.
    @display(ordering='order', description=_('Order'))
    def index_order(self, obj):
        return mark_safe(
            '<div class="w-orderable__item__handle button button-small button--icon handle text-replace">'
            '<svg class="icon icon-grip default" style="padding: 0px;" aria-hidden="true">'
            '<use href="#icon-grip"></use>'
            '</svg>'
            '</div>',
        )

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get_as_type(AttributeType)
        choice_option_panels = insert_model_translation_panels(
            AttributeTypeChoiceOption,
            self.choice_option_panels,
            request,
            instance,
        )

        if instance.pk is not None:
            usage_by_option = _get_choice_option_usage(instance)
            if usage_by_option:
                choice_option_panels = [*choice_option_panels, ChoiceOptionUsagePanel(usage_by_option)]

        creating = instance.pk is None
        if not creating and instance and AttributeTypeWrapper.from_model_instance(instance).attributes.exists():
            format_field_panel = FieldPanel(
                'format',
                read_only=True,
                help_text=_(
                    "This field already has values. If you want to change the format, you need to delete the existing "
                    "values first.",
                ),
            )
        else:
            format_field_panel = FieldPanel('format')

        panels = [
            FieldPanel('name'),
            FieldPanel('help_text'),
            format_field_panel,
            FieldPanel('unit'),
            FieldPanel('attribute_category_type', widget=CategoryTypeChooser),
            CondensedInlinePanel('choice_options', heading=_("Choice options"), panels=choice_option_panels),
            FieldPanel('show_choice_names'),
            FieldPanel('has_zero_option'),
            FieldPanel('max_length'),
            FieldPanel('instances_visible_for'),
            FieldPanel('instances_editable_by'),
            FieldPanel('show_in_reporting_tab'),
        ]
        panels = insert_model_translation_panels(AttributeType, panels, request, instance)
        if instance is None or instance.object_content_type_id is None:
            content_type_id = request.GET['content_type']
        else:
            content_type_id = instance.object_content_type_id
        content_type = ContentType.objects.get(pk=content_type_id)

        base_form_class = AttributeTypeForm  # For action attribute types, we use a special subclass
        if (content_type.app_label, content_type.model) == ('actions', 'action'):
            # This attribute types has scope 'plan' and we automatically set the scope in AttributeTypeCreateView, so we
            # don't add a panel for choosing a plan.
            base_form_class = ActionAttributeTypeForm
            panels.append(FieldPanel('action_list_filter_section'))
            panels.append(FieldPanel('action_detail_content_section'))
        elif (content_type.app_label, content_type.model) == ('actions', 'category'):
            panels.insert(0, FieldPanel('scope_id', widget=CategoryTypeChooser, heading=_("Category type")))
        elif (content_type.app_label, content_type.model) == ('actions', 'pledge'):
            # This attribute types has scope 'plan' and we automatically set the scope in AttributeTypeCreateView, so we
            # don't add a panel for choosing a plan.
            # Remove show_in_reporting_tab since pledges are not used with reporting
            panels = [p for p in panels if getattr(p, 'field_name', None) != 'show_in_reporting_tab']
        else:
            raise Exception(f"Invalid content type {content_type.app_label}.{content_type.model}")

        tabs = [ObjectList(panels, heading=_('General'))]

        handler = AttributeTypeEditHandler(tabs, base_form_class=base_form_class)
        return handler

    def get_menu_item(self, order=None):
        return AttributeTypeAdminMenuItem(self, order or self.get_menu_order())

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = user_or_bust(request.user)
        plan = user.get_active_admin_plan()
        action_ct = ContentType.objects.get(app_label='actions', model='action')
        category_ct = ContentType.objects.get(app_label='actions', model='category')
        pledge_ct = ContentType.objects.get(app_label='actions', model='pledge')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        category_type_ct = ContentType.objects.get(app_label='actions', model='categorytype')
        category_types_in_plan = plan.category_types.all()
        # Attribute types for actions of the active plan
        actions_q = Q(object_content_type=action_ct) & Q(scope_content_type=plan_ct) & Q(scope_id=plan.id)
        # Attribute types for categories whose category type is the active plan
        categories_q = (
            Q(object_content_type=category_ct)
            & Q(scope_content_type=category_type_ct)
            & Q(scope_id__in=category_types_in_plan)
        )
        # Attribute types for pledges of the active plan
        pledges_q = Q(object_content_type=pledge_ct) & Q(scope_content_type=plan_ct) & Q(scope_id=plan.id)
        q = actions_q | categories_q
        if plan.features.enable_community_engagement:
            q |= pledges_q
        return qs.filter(q)
