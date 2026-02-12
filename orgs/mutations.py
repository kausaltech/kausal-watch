from __future__ import annotations

from typing import TYPE_CHECKING, cast

import strawberry as sb

from kausal_common.users import user_or_none

from orgs.models import Organization
from orgs.schema import OrganizationNode  # noqa: TC001

if TYPE_CHECKING:
    from aplans.graphql_types import SBInfo


@sb.input
class OrganizationInput:
    name: str = sb.field(description="The official name of the organization")
    abbreviation: str | None = sb.field(
        default=None,
        description="Short abbreviation (e.g. \"NASA\", \"YM\")",
    )
    parent_id: sb.ID | None = sb.field(
        default=None,
        description="ID of the parent organization; omit for a root organization",
    )
    primary_language: str = sb.field(
        default='en-US',
        description='Primary language code (ISO 639-1, e.g. "en-US", "fi", "de-CH").',
    )


class ValidationError(Exception):
    pass


@sb.type
class OrganizationMutations:
    @sb.mutation(description="Create a new organization")
    def create_organization(self, info: SBInfo, input: OrganizationInput) -> OrganizationNode:
        user = user_or_none(info.context.user)
        if user is None:
            raise PermissionError("Authentication required for this operation.")
        if not user.is_superuser:
            raise PermissionError("Superuser required for this operation.")

        org = Organization(
            name=input.name,
            abbreviation=input.abbreviation or '',
            primary_language=input.primary_language,
        )

        if input.parent_id:
            parent = Organization.objects.filter(pk=input.parent_id).first()
            if parent is None:
                raise ValidationError(f"Parent organization with ID {input.parent_id} not found.")
            org = parent.add_child(instance=org)
        else:
            org = Organization.add_root(instance=org)

        return cast('OrganizationNode', org)  # pyright: ignore[reportInvalidCast]
