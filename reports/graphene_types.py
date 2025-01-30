from dataclasses import dataclass
from functools import cache
from typing import Type

import graphene

from grapple.registry import registry as grapple_registry
from grapple.types.streamfield import StreamFieldBlock

from aplans.graphql_types import register_graphene_node


def get_report_field_block() -> StreamFieldBlock | None:
    from reports.blocks.action_content import ReportFieldBlock
    return grapple_registry.streamfield_blocks.get(ReportFieldBlock)


class ReportValueInterface(graphene.Interface):
    field = graphene.NonNull(get_report_field_block)


class ActionReportValue(graphene.ObjectType):
    pass


@dataclass(eq=True, frozen=True)
class GrapheneValueClassProperties:
    class_name: str
    value_field_name: str
    value_field_type: str


@cache
def generate_graphene_report_value_node_class(
        properties: GrapheneValueClassProperties,
) -> type[ActionReportValue]:
    """
    Generates a class representing a report value, and registers it as graphene node
    The class would look something like this if created manually:

        @register_graphene_node
        class ActionResponsiblePartyReportValue(ActionReportValue):
            responsible_party = graphene.Field('actions.schema.ActionResponsiblePartyNode')
            class Meta:
                interfaces = (ReportValueInterface,)

    It implements the  ReportValueInterface graphene interface and also has a custom field
    with  a custom name for retrieving  the value of this report field.
    """
    Meta_ = type('Meta', (), {'interfaces': (ReportValueInterface,)})
    Class = type(
        properties.class_name,
        (ActionReportValue,),
        {
            'Meta': Meta_,
            properties.value_field_name: graphene.Field(properties.value_field_type),
        },
    )
    globals()[properties.class_name] = Class
    register_graphene_node(Class)
    return Class
