from __future__ import annotations

import dataclasses
from typing import Any

import strawberry
from strawberry.tools import merge_types
from strawberry.types.field import StrawberryField

from kausal_common.deployment import test_mode_enabled
from kausal_common.strawberry.registry import register_strawberry_type
from kausal_common.testing.schema import TestModeMutation, TestModeNotEnabledError

from aplans.schema import SBQuery, generate_schema

from actions.models.plan import Plan
from orgs.models import Organization


@strawberry.type
class BaseModelType:
    def __init__(self, obj: Any, private_field_name: str):
        setattr(self, private_field_name, obj)
        proper_fields = [
            field.name for field in dataclasses.fields(self)
            if not isinstance(field, StrawberryField)
            and field.name != private_field_name
        ]
        for field in proper_fields:
            setattr(self, field, getattr(obj, field))


# FIXME: We have two GraphQL types for representing organizations -- this one and OrganizationNode (for Graphene). I'm
# not sure if or how we can use a Graphene type in a Strawberry query / mutation.
@register_strawberry_type
@strawberry.type
class OrganizationType(BaseModelType):
    id: int
    uuid: str
    name: str

    _org: strawberry.Private[Organization]

    def __init__(self, organization: Organization):
        super().__init__(organization, '_org')


# FIXME: We have two GraphQL types for representing plans -- this one and PlanNode (for Graphene). I'm not sure if or
# how we can use a Graphene type in a Strawberry query / mutation.
@register_strawberry_type
@strawberry.type
class PlanType(BaseModelType):
    id: int
    identifier: str

    _plan: strawberry.Private[Plan]

    def __init__(self, plan: Plan):
        super().__init__(plan, '_plan')


@strawberry.type
class WatchTestModeMutation(TestModeMutation):
    # FIXME: We already have such a mutation in orgs/schema.py!?
    @strawberry.mutation
    def create_organization(self, name: str) -> OrganizationType:
        org = Organization(name=name)
        Organization.add_root(instance=org)
        return OrganizationType(org)

    @strawberry.mutation
    def create_plan(self, identifier: str, name: str, organization_uuid: str) -> PlanType:
        org = Organization.objects.get(uuid=organization_uuid)
        plan = Plan.objects.create(organization=org, identifier=identifier, name=name)
        return PlanType(plan)


@strawberry.type
class WatchTestModeMutations:
    @strawberry.field
    def test_mode(self) -> WatchTestModeMutation:
        if not test_mode_enabled():
            raise TestModeNotEnabledError()
        return WatchTestModeMutation()


SB_MUTATION_TYPES: list[type] = []
if test_mode_enabled():
    SB_MUTATION_TYPES.append(WatchTestModeMutations)

SBMutation: type | None = None
if SB_MUTATION_TYPES:
    SBMutation = merge_types('Mutation', tuple(SB_MUTATION_TYPES))

sb_schema, schema = generate_schema(SBQuery, SBMutation)
