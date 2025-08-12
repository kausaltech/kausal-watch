from __future__ import annotations

from typing import TYPE_CHECKING

import graphene

from aplans.graphql_types import register_graphene_interface

if TYPE_CHECKING:
    from aplans.graphql_types import GQLInfo


class FieldBlockMetaData(graphene.ObjectType):
    restricted = graphene.Boolean()
    hidden = graphene.Boolean()

    @staticmethod
    def resolve_restricted(root: dict[str, bool], *args, **kwargs) -> bool:
        return root['restricted']

    @staticmethod
    def resolve_hidden(root, *args, **kwargs) -> bool:
        return root['hidden']


class FieldBlockMetaField:
    meta = graphene.Field(FieldBlockMetaData)


@register_graphene_interface
class FieldBlockMetaInterface(graphene.Interface):
    meta = graphene.Field(FieldBlockMetaData)

    @staticmethod
    def resolve_meta(root, info: GQLInfo, *args, **kwargs) -> dict[str, bool]:
        attribute_type = root.value.get('attribute_type') if root.value else None
        user = info.context.user
        plan = info.context.active_plan
        restricted = hidden = False
        if attribute_type:
            # TODO: implement for builtin fields as well
            hidden = not attribute_type.is_instance_visible_for(user, plan, None)
            restricted = attribute_type.instances_visible_for != attribute_type.VisibleFor.PUBLIC
        return {
            'restricted': restricted,
            'hidden': hidden,
        }
