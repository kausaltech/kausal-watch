from __future__ import annotations

from typing import TYPE_CHECKING, Unpack, overload

from kausal_common.strawberry.helpers import get_or_error
from kausal_common.strawberry.mutations import (
    mutation as base_mutation,
    parse_input,
    prepare_create_update,
    prepare_instance,
)
from kausal_common.users import user_or_none

from actions.models import Plan

from .graphql_types import SBInfo as Info

if TYPE_CHECKING:
    from strawberry.extensions import FieldExtension
    from strawberry_django.mutations.fields import DjangoMutationBase

    from kausal_common.strawberry.mutations import (
        MutationArgs,
        ResolverFunc,
    )


def get_plan_or_error(info: Info, plan_id: str) -> Plan:
    """
    Get a plan by id or identifier.

    Raises a GraphQL error if the plan is not found or not visible for the user.
    """
    user = user_or_none(info.context.user)
    qs = Plan.objects.qs.visible_for_user(user).by_id_or_identifier(plan_id)
    plan = get_or_error(info, qs)
    return plan


@overload
def mutation(*, extensions: list[FieldExtension] | None = None, **kwargs: Unpack[MutationArgs]) -> DjangoMutationBase: ...

@overload
def mutation(resolver: ResolverFunc, **kwargs: Unpack[MutationArgs]) -> DjangoMutationBase: ...


def mutation(
    resolver: ResolverFunc | None = None, *, extensions: list[FieldExtension] | None = None, **kwargs: Unpack[MutationArgs]
) -> DjangoMutationBase:
    ret = base_mutation(extensions=extensions, **kwargs)
    if resolver is not None:
        return ret(resolver)
    return ret


__all__ = ['Info', 'get_plan_or_error', 'mutation', 'parse_input', 'prepare_create_update', 'prepare_instance']

