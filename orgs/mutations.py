from __future__ import annotations

from typing import cast

import strawberry as sb
from django.forms import ValidationError

from kausal_common.strawberry.permissions import SuperuserOnly
from kausal_common.users import user_or_bust

from aplans import gql

from orgs.models import Organization
from orgs.schema import OrganizationNode


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


@sb.type
class OrganizationMutations:
    @gql.mutation(description="Create a new organization", permission_classes=[SuperuserOnly])
    def create_organization(self, info: gql.Info, input: OrganizationInput) -> OrganizationNode:
        org, _, _ = gql.prepare_create_update(info, Organization, input)
        user = user_or_bust(info.context.user)
        if input.parent_id:
            parent = Organization.get_parent_choices(user=user).filter(pk=input.parent_id).first()
            if parent is None:
                raise ValidationError({'parent_id':f"Parent organization with ID {input.parent_id} not found."})
            org = parent.add_child(instance=org)
        else:
            org = Organization.add_root(instance=org)

        return cast('OrganizationNode', org)  # pyright: ignore[reportInvalidCast]
