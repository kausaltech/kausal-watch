from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString, GraphQLInt
from wagtail.core import blocks

from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType


@register_streamfield_block
class ActionAttributeTypeFilterBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True, label=_("Attribute type"))
    show_all_label = blocks.CharBlock(required=False, label=_("Label for 'show all'"))

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLString('show_all_label'),
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]

    class Meta:
        label = _("Attribute")


@register_streamfield_block
class CategoryTypeFilterBlock(blocks.StructBlock):
    style = blocks.ChoiceBlock(choices=[
        ('dropdown', _('Dropdown')),
        ('buttons', _('Buttons')),
    ], label=_("Style"), default='dropdown')
    show_all_label = blocks.CharBlock(required=False, label=_("Label for 'show all'"))
    category_type = CategoryTypeChooserBlock(required=True, label=_("Category type"))
    depth = blocks.IntegerBlock(
        required=False,
        help_text=_("How many levels of category hierarchy to show"),
        min_value=1
    )

    model_instance_container_blocks = {
        CategoryType: 'category_type',
    }

    graphql_fields = [
        GraphQLString('style'),
        GraphQLString('show_all_label'),
        GraphQLInt('depth'),
        GraphQLForeignKey('category_type', CategoryType)
    ]

    class Meta:
        label = _("Category")


class FilterBlock(blocks.StaticBlock):
    graphql_fields = []

    def get_admin_text(self):
        return _("Filter: %(filter_label)s") % dict(filter_label=self.meta.label)


@register_streamfield_block
class ResponsiblePartyFilterBlock(FilterBlock):
    class Meta:
        label = _("responsible party")


@register_streamfield_block
class PrimaryOrganizationFilterBlock(FilterBlock):
    class Meta:
        label = _("primary organization")


@register_streamfield_block
class ActionImplementationPhaseFilterBlock(FilterBlock):
    class Meta:
        label = _("implementation phase")


@register_streamfield_block
class ActionScheduleFilterBlock(FilterBlock):
    class Meta:
        label = _("schedule")


@register_streamfield_block
class ActionListFilterBlock(ActionListPageBlockPresenceMixin, blocks.StreamBlock):
    responsible_party = ResponsiblePartyFilterBlock()
    primary_org = PrimaryOrganizationFilterBlock()
    implementation_phase = ActionImplementationPhaseFilterBlock()
    schedule = ActionScheduleFilterBlock()
    attribute = ActionAttributeTypeFilterBlock()
    category = CategoryTypeFilterBlock()

    model_instance_container_blocks = {
        AttributeType: 'attribute',
        CategoryType: 'category',
    }

    graphql_types = [
        ResponsiblePartyFilterBlock, PrimaryOrganizationFilterBlock, ActionImplementationPhaseFilterBlock,
        ActionScheduleFilterBlock, ActionAttributeTypeFilterBlock, CategoryTypeFilterBlock
    ]
