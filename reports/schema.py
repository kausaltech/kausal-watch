import graphene
from graphql.error import GraphQLError
from grapple.registry import registry as grapple_registry

from aplans.graphql_types import DjangoNode, register_django_node
from aplans.utils import public_fields
from actions.models import Action
from reports.blocks.action_content import ReportFieldBlock, ReportValueInterface
from reports.models import Report, ReportType


@register_django_node
class ReportNode(DjangoNode):
    fields = graphene.List(graphene.NonNull(lambda: grapple_registry.streamfield_blocks.get(ReportFieldBlock)))
    values_for_action = graphene.List(
        graphene.NonNull(ReportValueInterface),
        # Either action_id or action_identifier must be specified
        action_id=graphene.ID(),
        action_identifier=graphene.ID(),
    )

    class Meta:
        model = Report
        fields = public_fields(Report)

    def resolve_values_for_action(root, info, action_id=None, action_identifier=None):
        if (action_id and action_identifier) or not (action_id or action_identifier):
            raise GraphQLError("You must specify either actionId or actionIdentifier")
        plan_actions = Action.objects.filter(plan=root.type.plan)
        if action_id:
            action = plan_actions.get(id=action_id)
        else:
            action = plan_actions.get(identifier=action_identifier)
        snapshot = action.get_latest_snapshot(root)
        return [field.block.graphql_value_for_action_snapshot(field, snapshot) for field in root.fields]


@register_django_node
class ReportTypeNode(DjangoNode):
    class Meta:
        model = ReportType
        fields = public_fields(ReportType)
