from __future__ import annotations

import reversion
import typing
import uuid
from django.conf import settings
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import Q
from django.utils import translation
from django.utils.translation import gettext_lazy as _, override
from django.utils.text import format_lazy
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.translator import get_i18n_field
from modeltrans.utils import get_available_languages
from wagtail.models import Page, Collection
from wagtailsvg.models import Svg

from ..attributes import AttributeType
from .attributes import AttributeType as AttributeTypeModel, ModelWithAttributes
from aplans.utils import (
    IdentifierField, InstancesEditableByMixin, OrderedModel, PlanRelatedModel, ReferenceIndexedModelMixin,
    generate_identifier, validate_css_color, get_supported_languages
)

if typing.TYPE_CHECKING:
    from django.db.models.manager import RelatedManager


class CategoryTypeBase(models.Model):
    class SelectWidget(models.TextChoices):
        SINGLE = 'single', _('Single')
        MULTIPLE = 'multiple', _('Multiple')

    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField()
    hide_category_identifiers = models.BooleanField(
        default=False, verbose_name=_('hide category identifiers'),
        help_text=_("Set if the categories do not have meaningful identifiers")
    )
    lead_paragraph = models.TextField(verbose_name=_('lead paragraph'), null=True, blank=True)
    help_text = models.TextField(verbose_name=_('help text'), blank=True)
    usable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('usable for action categorization'),
    )
    usable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('usable for indicator categorization'),
    )
    editable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('editable for actions'),
    )
    editable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('editable for indicators'),
    )
    select_widget = models.CharField(
        max_length=30,
        choices=SelectWidget.choices,
        default=SelectWidget.SINGLE,
        verbose_name=_('single or multiple selection'),
        help_text=(
            format_lazy(
                _('Choose "{choice_multiple}" only if more than one category can be selected at a time, '
                  'otherwise choose "{choice_single}" which is the default.'),
                choice_multiple=SelectWidget.MULTIPLE.label,
                choice_single=SelectWidget.SINGLE.label
            )
        )
    )

    public_fields = [
        'name', 'identifier', 'lead_paragraph', 'help_text', 'hide_category_identifiers',
        'usable_for_indicators', 'usable_for_actions',
        'editable_for_actions', 'editable_for_indicators',
    ]

    class Meta:
        abstract = True


@reversion.register()
class CommonCategoryType(CategoryTypeBase):
    has_collection = models.BooleanField(
        default=False, verbose_name=_('has a collection'),
        help_text=_('Set if this category type should have its own collection for images')
    )
    # collection for photos and icons
    collection = models.OneToOneField(
        Collection, null=True, on_delete=models.PROTECT, editable=False, related_name='common_category_type',
    )

    primary_language = models.CharField(max_length=20, choices=get_supported_languages(), default='en')
    i18n = TranslationField(fields=('name', 'lead_paragraph'), default_language_field='primary_language')

    public_fields = CategoryTypeBase.public_fields + [
        'categories'
    ]

    class Meta:
        unique_together = (('identifier',),)
        verbose_name = _('common category type')
        verbose_name_plural = _('common category types')
        ordering = ('identifier',)

    def __str__(self):
        return f"{self.name}: {self.identifier}"

    def instantiate_for_plan(self, plan):
        """Create category type corresponding to this one and link it to the given plan."""
        if plan.category_types.filter(common=self).exists():
            raise Exception(f"Instantiation of common category type '{self}' for plan '{plan}' exists already")
        translated_fields = get_i18n_field(CategoryType).fields
        other_languages = [lang.replace('-', '_')
                           for lang in get_available_languages()
                           if lang != plan.primary_language]
        # Inherit fields from CategoryTypeBase, but instead of `name` we want `name_<lang>`, where `<lang>` is the
        # primary language of the the active plan, and the same for other translated fields.
        # TODO: Something like this should be put in modeltrans to implement changing the per-instance default
        # language.
        # TODO: Duplicated in CommonCategory.instantiate_for_category_type()
        # Temporarily override language so that the `_i18n` suffix field falls back to the original field
        with translation.override(plan.primary_language):
            translated_values = {field: getattr(self, f'{field}_i18n') for field in translated_fields}
        for field in translated_fields:
            for lang in other_languages:
                value = getattr(self, f'{field}_{lang}')
                if value:
                    translated_values[f'{field}_{lang}'] = value
        inherited_fields = [f.name for f in CategoryTypeBase._meta.fields if f.name not in translated_fields]
        inherited_values = {field: getattr(self, field) for field in inherited_fields}
        return plan.category_types.create(common=self, **inherited_values, **translated_values)

    def save(self, *args, **kwargs):
        ret = super().save(*args, **kwargs)
        if self.has_collection and self.collection is None:
            with transaction.atomic():
                ct_coll = Collection.objects.filter(name=settings.COMMON_CATEGORIES_COLLECTION).first()
                if ct_coll is None:
                    ct_coll = Collection.get_first_root_node().add_child(name=settings.COMMON_CATEGORIES_COLLECTION)
                obj = ct_coll.add_child(name=self.name)
                self.collection = obj
                self.save(update_fields=['collection'])
        return ret


@reversion.register()
class CategoryType(
    InstancesEditableByMixin, ReferenceIndexedModelMixin, CategoryTypeBase, ClusterableModel, PlanRelatedModel
):
    """Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='category_types')
    common = models.ForeignKey(
        CommonCategoryType, blank=True, null=True, on_delete=models.PROTECT,
        verbose_name=_('common category type'), related_name='category_type_instances'
    )
    synchronize_with_pages = models.BooleanField(
        default=False, verbose_name=_("synchronize with pages"),
        help_text=_("Set if categories of this type should be synchronized with pages")
    )
    i18n = TranslationField(fields=('name', 'lead_paragraph'), default_language_field='plan__primary_language')

    attribute_types = GenericRelation(
        to='actions.AttributeType',
        related_query_name='category_type',
        content_type_field='scope_content_type',
        object_id_field='scope_id',
    )

    categories: models.QuerySet[Category]

    public_fields = CategoryTypeBase.public_fields + [
        'id', 'plan', 'common', 'levels', 'categories', 'hide_category_identifiers'
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'name')
        verbose_name = _('category type')
        verbose_name_plural = _('category types')

    def __str__(self):
        return "%s (%s:%s)" % (self.name, self.plan.identifier, self.identifier)

    @transaction.atomic
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.synchronize_with_pages:
            self.synchronize_pages()

    def synchronize_pages(self):
        from pages.models import CategoryTypePage
        for root_page in self.plan.root_page.get_translations(inclusive=True):
            with override(root_page.locale.language_code):
                try:
                    ct_pages = self.category_type_pages.all()  # pages for this category type in any language
                    ct_page = root_page.get_children().type(CategoryTypePage).get(id__in=ct_pages)
                except Page.DoesNotExist:
                    ct_page = CategoryTypePage(
                        category_type=self, title=self.name_i18n, show_in_menus=True, show_in_footer=True
                    )
                    root_page.add_child(instance=ct_page)
            for category in self.categories.filter(parent__isnull=True):
                category.synchronize_pages(ct_page)


@reversion.register()
class CategoryLevel(OrderedModel):
    """Hierarchy level within a CategoryType.

    Root level has order=0, first child level order=1 and so on.
    """
    type = ParentalKey(
        CategoryType, on_delete=models.CASCADE, related_name='levels',
        verbose_name=_('type')
    )
    name = models.CharField(max_length=100, verbose_name=_('name'))
    name_plural = models.CharField(max_length=100, verbose_name=_('plural name'), null=True, blank=True)

    i18n = TranslationField(fields=('name',), default_language_field='type__plan__primary_language')

    public_fields = [
        'id', 'name', 'name_plural', 'order', 'type',
    ]

    class Meta:
        unique_together = (('type', 'order'),)
        verbose_name = _('category level')
        verbose_name_plural = _('category levels')
        ordering = ('type', 'order')

    def __str__(self):
        return self.name


class CategoryBase(OrderedModel):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    identifier = IdentifierField()
    name = models.CharField(max_length=200, verbose_name=_('name'))
    lead_paragraph = models.TextField(
        max_length=300, blank=True, verbose_name=_('lead paragraph')
    )
    image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    color = models.CharField(
        max_length=50, blank=True, null=True, verbose_name=_('theme color'),
        help_text=_('Set if the category has a theme color'),
        validators=[validate_css_color]
    )
    help_text = models.TextField(verbose_name=_('help text'), blank=True)

    public_fields = [
        'id', 'uuid', 'identifier', 'name', 'lead_paragraph', 'image', 'color', 'help_text', 'order',
    ]

    class Meta:
        abstract = True


@reversion.register()
class CommonCategory(CategoryBase, ClusterableModel):
    type = models.ForeignKey(
        CommonCategoryType,  on_delete=models.CASCADE, related_name='categories',
        verbose_name=_('type')
    )

    category_instances: RelatedManager[Category]

    i18n = TranslationField(
        fields=('name', 'lead_paragraph', 'help_text'),
        default_language_field='type__primary_language'
    )

    public_fields = CategoryBase.public_fields + [
        'type', 'category_instances'
    ]

    class Meta:
        unique_together = (('type', 'identifier'),)
        ordering = ('type', 'order')
        verbose_name = _('common category')
        verbose_name_plural = _('common categories')

    def __str__(self):
        return '[%s] %s' % (self.identifier, self.name)

    def instantiate_for_category_type(self, category_type):
        """Create category corresponding to this one and set its type to the given one."""
        if category_type.categories.filter(common=self).exists():
            raise Exception(f"Instantiation of common category '{self}' for category type '{category_type}' exists "
                            "already")
        translated_fields = get_i18n_field(Category).fields
        other_languages = [lang.replace('-', '_')
                           for lang in get_available_languages()
                           if lang != category_type.plan.primary_language]
        # Inherit fields from CategoryBase, but instead of `name` we want `name_<lang>`, where `<lang>` is the primary
        # language of the the active plan, and the same for other translated fields.
        # TODO: Duplicated in CommonCategoryType.instantiate_for_plan()
        # Temporarily override language so that the `_i18n` suffix field falls back to the original field
        with translation.override(category_type.plan.primary_language):
            translated_values = {field: getattr(self, f'{field}_i18n') for field in translated_fields}
        for field in translated_fields:
            for lang in other_languages:
                value = getattr(self, f'{field}_{lang}')
                if value:
                    translated_values[f'{field}_{lang}'] = value
        inherited_fields = [f.name for f in CategoryBase._meta.fields if f.name not in translated_fields + ('uuid',)]
        inherited_values = {field: getattr(self, field) for field in inherited_fields}
        return category_type.categories.create(common=self, **inherited_values, **translated_values)

    def get_icon(self, language=None):
        """Get CommonCategoryIcon in the given language, falling back to an icon without a language."""
        if language is None:
            try:
                return self.icons.get(language__isnull=True)
            except CommonCategoryIcon.DoesNotExist:
                return None
        # At this point, language is not None
        try:
            return self.icons.get(language__iexact=language)
        except CommonCategoryIcon.DoesNotExist:
            return self.get_icon(language=None)


@reversion.register(follow=ModelWithAttributes.REVERSION_FOLLOW)
class Category(ModelWithAttributes, CategoryBase, ClusterableModel, PlanRelatedModel):
    """A category for actions and indicators."""

    type = models.ForeignKey(
        CategoryType, on_delete=models.PROTECT, related_name='categories',
        verbose_name=_('type')
    )
    common = models.ForeignKey(
        CommonCategory, on_delete=models.PROTECT, related_name='category_instances',
        null=True, blank=True, verbose_name=_('common category'),
    )
    external_identifier = models.CharField(max_length=50, blank=True, null=True, editable=False)
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
        verbose_name=_('parent category')
    )

    i18n = TranslationField(
        fields=('name', 'lead_paragraph', 'help_text'),
        default_language_field='type__plan__primary_language'
    )

    public_fields = CategoryBase.public_fields + [
        'type', 'common', 'external_identifier', 'parent', 'children', 'category_pages', 'indicators',
    ]

    class Meta:
        unique_together = (('type', 'identifier'), ('type', 'external_identifier'))
        verbose_name = _('category')
        verbose_name_plural = _('categories')
        ordering = ('type', 'order')

    def clean(self):
        if self.parent_id is not None:
            seen_categories = {self.id}
            obj = self.parent
            while obj is not None:
                if obj.id in seen_categories:
                    raise ValidationError({'parent': _('Parent forms a loop. Leave empty if top-level category.')})
                seen_categories.add(obj.id)
                obj = obj.parent

            if self.parent.type != self.type:
                raise ValidationError({'parent': _('Parent must be of same type')})

    def get_plans(self):
        return [self.type.plan]

    @classmethod
    def filter_by_plan(cls, plan, qs):
        return qs.filter(type__plan=plan)

    def set_plan(self, plan):
        # The right plan should be set through CategoryType relation, so
        # we do nothing here.
        pass

    def generate_identifier(self):
        self.identifier = generate_identifier(self.type.categories.all(), 'c', 'identifier')

    def synchronize_pages(self, parent):
        """Create page for this category, then for all its children."""
        page = self.synchronize_page(parent)
        for child in self.children.all():
            child.synchronize_pages(page)

    def synchronize_page(self, parent):
        # If the page already exists, its existing parent page might be different from `parent` because the category may
        # have moved in the hierarchy
        from pages.models import CategoryPage
        is_root = self.parent is None
        with override(parent.locale.language_code):
            try:
                page = self.category_pages.get(locale=parent.locale)
            except CategoryPage.DoesNotExist:
                body = [('action_list', {'category_filter': self})]
                if self.children.exists():
                    # TODO: Make heading customizable
                    category_list_block = ('category_list', {'heading': _("Subcategories"), 'style': 'cards'})
                    body.insert(0, category_list_block)
                page = CategoryPage(
                    category=self, title=self.name_i18n, show_in_menus=is_root, show_in_footer=is_root, body=body,
                )
                parent.add_child(instance=page)
            else:
                update_page_parent = page.get_parent().specific != parent
                prev_cat = Category.objects.filter(type=self.type, parent=self.parent, order__lt=self.order).last()
                if prev_cat is None:
                    prev_cat_page = None
                    update_page_sibling = page.get_prev_sibling() is not None
                else:
                    prev_cat_page = prev_cat.category_pages.filter(locale=parent.locale).first()
                    update_page_sibling = page.get_prev_sibling() != prev_cat_page
                if update_page_parent or update_page_sibling:
                    if prev_cat_page:
                        page.move(prev_cat_page, 'right')
                    else:
                        page.move(parent, 'first-child')
                    # page.get_parent() (or sibling data) is now stale, but page.refresh_from_db() won't cut it with
                    # treebeard
                    page = Page.objects.get(pk=page.pk)
                page.title = self.name_i18n
                page.draft_title = self.name_i18n
                page.show_in_menus = is_root
                page.show_in_footer = is_root
                page.save()
        return page

    @transaction.atomic()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.type.synchronize_with_pages:
            # We need to synchronize multiple page trees if there are multiple languages
            if self.parent:
                parent_pages = self.parent.category_pages.all()
            else:
                parent_pages = self.type.category_type_pages.all()
            for parent_page in parent_pages:
                self.synchronize_page(parent_page)

    def __str__(self):
        if self.identifier and self.type and not self.type.hide_category_identifiers:
            return "%s %s" % (self.identifier, self.name)
        else:
            return self.name

    def _get_icon_without_fallback_to_common_category(self, language=None):
        if language is None:
            try:
                return self.icons.get(language__isnull=True)
            except CategoryIcon.DoesNotExist:
                return None
        # At this point, language is not None
        try:
            return self.icons.get(language=language)
        except CategoryIcon.DoesNotExist:
            return self._get_icon_without_fallback_to_common_category(language=None)

    def get_icon(self, language=None):
        """Get CategoryIcon in the given language, falling back to no language and the common category's icon.

        If self has an icon (no matter the language, if any), does not fall back to the common category's icon.
        Otherwise falls back to the common category's icon in the requested language and finally to the common
        category's icon without a language.
        """
        if self.icons.exists():
            return self._get_icon_without_fallback_to_common_category(language)
        if self.common:
            return self.common.get_icon(language)
        return None

    def get_attribute_type_by_identifier(self, identifier):
        return self.type.attribute_types.get(identifier=identifier)

    def get_visible_attribute_types(self, user):
        category_ct = ContentType.objects.get_for_model(Category)
        category_type_ct = ContentType.objects.get_for_model(self.type)
        attribute_types = AttributeTypeModel.objects.filter(
            object_content_type=category_ct,
            scope_content_type=category_type_ct,
            scope_id=self.type.id,
        )
        attribute_types = (at for at in attribute_types if at.are_instances_visible_for(user, self.type.plan))
        # Convert to wrapper objects
        return [AttributeType.from_model_instance(at) for at in attribute_types]

    def get_attribute_panels(self, user):
        # Return a triple `(main_panels, i18n_panels)`, where `main_panels` is a list of panels to be put on the main
        # tab, and `i18n_panels` is a dict mapping a non-primary language to a list of panels to be put on the tab for
        # that language.
        main_panels = []
        i18n_panels = {}
        attribute_types = self.get_visible_attribute_types(user)
        plan = user.get_active_admin_plan()  # not sure if this is reasonable...
        for attribute_type in attribute_types:
            fields = attribute_type.get_form_fields(user, plan, self)
            for field in fields:
                if field.language:
                    i18n_panels.setdefault(field.language, []).append(field.get_panel())
                else:
                    main_panels.append(field.get_panel())
        return (main_panels, i18n_panels)

    def get_siblings(self, force_refresh=False):
        return Category.objects.filter(type=self.type, parent=self.parent)

    def get_prev_sibling(self):
        # TODO: Refactor duplicated code in Action
        previous_sibling = None
        for sibling in self.get_siblings():
            if sibling.id == self.id:
                return previous_sibling
            previous_sibling = sibling
        assert False  # should have returned above at some point

    def get_level(self) -> typing.Optional[CategoryLevel]:
        level = 0
        c = self
        while c.parent is not None:
            level += 1
            if level > 50:
                raise Exception("Maximum category hierarchy depth exceeded")
            c = c.parent
        return self.type.levels.filter(order=level).first()


class Icon(models.Model):
    # When subclassing, remember to set Meta.constraints = Icon.Meta.constraints
    svg = models.ForeignKey(Svg, blank=True, null=True, on_delete=models.CASCADE, related_name='+')
    image = models.ForeignKey('images.AplansImage', blank=True, null=True, on_delete=models.CASCADE, related_name='+')
    language = models.CharField(max_length=20, choices=get_supported_languages(), null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if (self.svg and self.image) or (not self.svg and not self.image):
            error = _('Either SVG or image must be set')
            raise ValidationError({'svg': error, 'image': error})

    class Meta:
        abstract = True
        constraints = [
            # svg XOR image must be set
            models.CheckConstraint(
                check=(Q(svg__isnull=True) & Q(image__isnull=False)) | (Q(svg__isnull=False) & Q(image__isnull=True)),
                name='%(app_label)s_%(class)s_svg_xor_image'
            ),
        ]


class CommonCategoryIcon(Icon):
    common_category = ParentalKey(
        CommonCategory, on_delete=models.CASCADE, related_name='icons',
        verbose_name=_('common category')
    )

    class Meta:
        unique_together = (('common_category', 'language'),)
        constraints = Icon.Meta.constraints

    def __str__(self):
        return '%s [%s]' % (self.common_category, self.language)


class CategoryIcon(Icon):
    category = ParentalKey(Category, on_delete=models.CASCADE, related_name='icons', verbose_name=_('category'))

    class Meta:
        unique_together = (('category', 'language'),)
        constraints = Icon.Meta.constraints

    def __str__(self):
        return '%s [%s]' % (self.category, self.language)
