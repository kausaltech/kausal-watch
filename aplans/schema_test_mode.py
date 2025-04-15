from __future__ import annotations

from typing import cast

import strawberry
from strawberry.tools import merge_types

import strawberry_django

from kausal_common.deployment import test_mode_enabled
from kausal_common.strawberry.registry import register_strawberry_type
from kausal_common.testing.schema import TestModeMutation, TestModeNotEnabledError

from aplans.schema import SBQuery, generate_schema

from actions.models.plan import Plan
from orgs.models import Organization


@register_strawberry_type
@strawberry.type
class ModelStubType:
    """
    Fields to return when creating a model instance with a test mode mutation.

    These fields must exist in all models created with test mode mutations. We return this generic type instead of the
    concrete created instance because at the moment most GraphQL types for our models are defined with Graphene and we
    can't use these types in Strawberry mutations. We'd have to duplicate a lot of types, which we avoid by not
    returning instances but only the fields defined here.
    """

    id: int


@strawberry.type
class WatchTestModeMutation(TestModeMutation):
    @strawberry_django.input_mutation
    def create_plan(self, identifier: str, name: str, organization_uuid: str) -> ModelStubType:
        org = Organization.objects.get(uuid=organization_uuid)
        plan = Plan.objects.create(organization=org, identifier=identifier, name=name)
        return cast(ModelStubType, plan)


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
