import graphene
from grapple.registry import registry as grapple_registry

from aplans.graphql_types import DjangoNode, register_django_node
from aplans.utils import public_fields
from reports.blocks.action_content import ReportFieldBlock
from reports.models import Report, ReportType


@register_django_node
class ReportNode(DjangoNode):
    fields = graphene.List(graphene.NonNull(lambda: grapple_registry.streamfield_blocks.get(ReportFieldBlock)))

    class Meta:
        model = Report
        fields = public_fields(Report)


@register_django_node
class ReportTypeNode(DjangoNode):
    class Meta:
        model = ReportType
        fields = public_fields(ReportType)
