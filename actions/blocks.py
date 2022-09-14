from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail.core import blocks
from actions.models.attributes import AttributeType

from actions.models.category import CategoryType

from .chooser import AttributeTypeChooser, CategoryChooser, CategoryTypeChooser
from .models import Category


class CategoryChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        return CategoryChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class CategoryTypeChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return CategoryType

    @cached_property
    def widget(self):
        return CategoryTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class AttributeTypeChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return AttributeType

    @cached_property
    def widget(self):
        return AttributeTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


@register_streamfield_block
class ActionHighlightsBlock(blocks.StaticBlock):
    pass


@register_streamfield_block
class ActionListBlock(blocks.StructBlock):
    category_filter = CategoryChooserBlock(label=_('Filter on category'))

    graphql_fields = [
        GraphQLForeignKey('category_filter', Category),
    ]


@register_streamfield_block
class CategoryListBlock(blocks.StructBlock):
    category_type = CategoryTypeChooserBlock(label=_('Category type'), required=False)
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)
    style = blocks.ChoiceBlock(choices=[
        ('cards', _('Cards')),
        ('table', _('Table')),
    ])

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLString('heading'),
        GraphQLString('lead'),
        GraphQLString('style'),
    ]


@register_streamfield_block
class CategoryTreeMapBlock(blocks.StructBlock):
    heading = blocks.CharBlock(classname='full title', label=_('Heading'), required=False)
    lead = blocks.RichTextBlock(label=_('Lead'), required=False)

    category_type = CategoryTypeChooserBlock(label=_('Category type'), required=True)
    value_attribute = AttributeTypeChooserBlock(label=_('Value attribute'), required=True)

    graphql_fields = [
        GraphQLForeignKey('category_type', CategoryType),
        GraphQLForeignKey('value_attribute', AttributeType),
        GraphQLString('heading'),
        GraphQLString('lead'),
    ]


@register_streamfield_block
class RelatedPlanListBlock(blocks.StaticBlock):
    pass
