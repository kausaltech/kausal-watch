from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString, GraphQLInt
from wagtail import blocks

from actions.blocks.choosers import ActionAttributeTypeChooserBlock, CategoryTypeChooserBlock
from actions.blocks.mixins import ActionListPageBlockPresenceMixin
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType


@register_streamfield_block
class ActionAttributeTypeFilterBlock(blocks.StructBlock):
    attribute_type = ActionAttributeTypeChooserBlock(required=True)
    show_all_label = blocks.CharBlock(required=False, label=_("Label for 'show all'"))

    model_instance_container_blocks = {
        AttributeType: 'attribute_type',
    }

    graphql_fields = [
        GraphQLString('show_all_label'),
        GraphQLForeignKey('attribute_type', AttributeType, required=True)
    ]

    class Meta:
        label = _("Field")


@register_streamfield_block
class CategoryTypeFilterBlock(blocks.StructBlock):
    style = blocks.ChoiceBlock(choices=[
        ('dropdown', _("Dropdown")),
        ('buttons', _("Buttons")),
    ], label=_("Style"), default='dropdown')
    show_all_label = blocks.CharBlock(required=False, label=_("Label for 'show all'"))
    category_type = CategoryTypeChooserBlock(required=True)
    depth = blocks.IntegerBlock(
        required=False,
        help_text=_("How many levels of category hierarchy to show"),
        min_value=1,
        label=_("Depth"),
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
        label = _("Responsible party")


@register_streamfield_block
class PrimaryOrganizationFilterBlock(FilterBlock):
    class Meta:
        label = _("Primary organization")


@register_streamfield_block
class ActionImplementationPhaseFilterBlock(FilterBlock):
    class Meta:
        label = _("Implementation phase")


@register_streamfield_block
class ActionStatusFilterBlock(FilterBlock):
    class Meta:
        label = _("Status")


@register_streamfield_block
class PlanFilterBlock(FilterBlock):
    class Meta:
        label = _("Plan")


@register_streamfield_block
class ActionScheduleFilterBlock(FilterBlock):
    class Meta:
        label = _("Schedule")


@register_streamfield_block
class ActionListFilterBlock(ActionListPageBlockPresenceMixin, blocks.StreamBlock):
    responsible_party = ResponsiblePartyFilterBlock()
    primary_org = PrimaryOrganizationFilterBlock()
    implementation_phase = ActionImplementationPhaseFilterBlock()
    status = ActionStatusFilterBlock()
    schedule = ActionScheduleFilterBlock()
    attribute = ActionAttributeTypeFilterBlock()
    category = CategoryTypeFilterBlock()
    plan = PlanFilterBlock()

    model_instance_container_blocks = {
        AttributeType: 'attribute',
        CategoryType: 'category',
    }

    graphql_types = [
        ResponsiblePartyFilterBlock, PrimaryOrganizationFilterBlock, ActionImplementationPhaseFilterBlock,
        ActionStatusFilterBlock, ActionScheduleFilterBlock, ActionAttributeTypeFilterBlock, CategoryTypeFilterBlock,
        PlanFilterBlock
    ]
