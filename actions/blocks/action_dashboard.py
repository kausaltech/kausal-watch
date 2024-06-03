from django.utils.translation import gettext_lazy as _
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLForeignKey, GraphQLString
from wagtail import blocks
import graphene
from actions.models.attributes import AttributeType

from actions.blocks.choosers import ActionAttributeTypeChooserBlock


class DashboardColumnInterface(graphene.Interface):
    column_label = graphene.String()


class ColumnBlockBase(blocks.StructBlock):
    column_label = blocks.CharBlock(
        required=False, label=_("Label"), help_text=_("Label for the column to be used instead of the default")
    )

    graphql_fields = [
        GraphQLString('column_label'),
    ]

    graphql_interfaces = (DashboardColumnInterface,)


@register_streamfield_block
class IdentifierColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Identifier")


@register_streamfield_block
class NameColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Name")


@register_streamfield_block
class ImplementationPhaseColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Implementation phase")


@register_streamfield_block
class StatusColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Status")


@register_streamfield_block
class TasksColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Tasks")


@register_streamfield_block
class ResponsiblePartiesColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Responsible parties")


@register_streamfield_block
class IndicatorsColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Indicators")


@register_streamfield_block
class UpdatedAtColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Updated at")


@register_streamfield_block
class OrganizationColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Organization")


@register_streamfield_block
class ImpactColumnBlock(ColumnBlockBase):
    class Meta:
        label = _("Impact")

@register_streamfield_block
class FieldColumnBlock(ColumnBlockBase):
    attribute_type = ActionAttributeTypeChooserBlock()
    class Meta:
        label = _("Field")

    graphql_fields = ColumnBlockBase.graphql_fields + [
        GraphQLForeignKey('attribute_type', AttributeType)
    ]


@register_streamfield_block
class ActionDashboardColumnBlock(blocks.StreamBlock):
    identifier = IdentifierColumnBlock()
    name = NameColumnBlock()
    implementation_phase = ImplementationPhaseColumnBlock()
    status = StatusColumnBlock()
    tasks = TasksColumnBlock()
    responsible_parties = ResponsiblePartiesColumnBlock()
    indicators = IndicatorsColumnBlock()
    updated_at = UpdatedAtColumnBlock()
    organization = OrganizationColumnBlock()
    imact = ImpactColumnBlock()
    field = FieldColumnBlock()

    graphql_types = [
        IdentifierColumnBlock, NameColumnBlock, ImplementationPhaseColumnBlock, StatusColumnBlock, TasksColumnBlock,
        ResponsiblePartiesColumnBlock, IndicatorsColumnBlock, UpdatedAtColumnBlock, OrganizationColumnBlock,
        ImpactColumnBlock, FieldColumnBlock
    ]
