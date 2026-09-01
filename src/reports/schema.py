from __future__ import annotations

from typing import TYPE_CHECKING

import graphene
from graphql.error import GraphQLError

import graphene_django_optimizer as gql_optimizer
from grapple.registry import registry as grapple_registry
from loguru import logger

from aplans.graphql_types import DjangoNode, register_django_node
from aplans.utils import public_fields

from actions.models import Action
from reports.blocks.action_content import ReportFieldBlock
from reports.graphene_types import ReportValueInterface
from reports.models import ActionSnapshot, Report, ReportType

if TYPE_CHECKING:
    from aplans.graphql_types import GQLInfo

    from actions.models.plan import Plan


@register_django_node
class ReportNode(DjangoNode[Report]):
    fields = graphene.List(graphene.NonNull(lambda: grapple_registry.streamfield_blocks.get(ReportFieldBlock)))
    # values_for_action is null if there is no snapshot for the specified action and the report
    values_for_action = graphene.List(
        graphene.NonNull(ReportValueInterface),
        # Either action_id or action_identifier must be specified
        action_id=graphene.ID(),
        action_identifier=graphene.ID(),
    )

    class Meta:
        model = Report
        fields = public_fields(Report)

    @staticmethod
    def resolve_values_for_action(
        root: Report, info: GQLInfo, action_id: str | None = None, action_identifier: str | None = None
    ) -> list[ReportValueInterface] | None:
        if (action_id and action_identifier) or not (action_id or action_identifier):
            raise GraphQLError('You must specify either actionId or actionIdentifier')
        if not root.type.plan.is_visible_for_user(info.context.user):
            return None
        plan_actions = Action.objects.filter(plan=root.type.plan)
        if action_id:
            action = plan_actions.get(id=action_id)
        else:
            action = plan_actions.get(identifier=action_identifier)
        try:
            snapshot = action.get_latest_snapshot(root)
        except ActionSnapshot.DoesNotExist:
            return None
        values = []
        for field in root.type.fields:
            if not hasattr(field.block, 'graphql_value_for_action_snapshot'):
                logger.warning(f'No functional graphql_value_for_action_snapshot method for {type(field.block)}')
                continue
            try:
                value = field.block.graphql_value_for_action_snapshot(field, snapshot)
            except NotImplementedError:
                logger.warning(f'No functional graphql_value_for_action_snapshot method for {type(field.block)}')
            else:
                values.append(value)
        return values


@register_django_node
class ReportTypeNode(DjangoNode[ReportType]):
    class Meta:
        model = ReportType
        fields = public_fields(ReportType)

    @staticmethod
    @gql_optimizer.resolver_hints(
        model_field='plan',
    )
    def resolve_plan(root: ReportType, info) -> Plan | None:
        return root.plan.get_if_visible(info.context.user)


class Query:
    pass
