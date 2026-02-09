from __future__ import annotations

from typing import TYPE_CHECKING, Annotated

import strawberry as sb
import strawberry_django

from kausal_common.users import user_or_bust, user_or_none

from actions.models import Action, Plan
from admin_site.models import Client
from orgs.models import Organization
from orgs.schema import OrganizationNode

if TYPE_CHECKING:
    from collections.abc import Iterable

    from django.db.models import QuerySet

    from aplans.graphql_types import SBInfo

    from actions.schema import ActionNode


@strawberry_django.type(Client, name='Client')
class ClientNode:
    id: sb.auto
    name: str
    logo: str
    url: str

    @classmethod
    def get_queryset(cls, qs: QuerySet[Client], info: SBInfo) -> QuerySet[Client]:
        user = user_or_none(info.context.user)
        if user is None or not user.is_superuser:
            return qs.none()
        return qs.order_by('name')


@sb.type
class AdminQuery:
    @strawberry_django.field(description='List of all clients', graphql_type=list[ClientNode])
    def clients(self) -> Iterable[Client]:
        return Client.objects.all().order_by('name')

    @strawberry_django.field(description='List of all organizations', graphql_type=list[OrganizationNode])
    def organizations(
        self,
        info: SBInfo,
        plan: Annotated[sb.ID | None, 'The plan identifier to filter organizations by'] = None,
        parent: Annotated[sb.ID | None, 'The parent organization ID'] = None,
        depth: Annotated[int, 'Number of descendant levels to include'] = 0,
        contains: Annotated[str | None, 'Search string to filter organizations by name (case-insensitive)'] = None,
    ) -> Iterable[Organization]:
        user = user_or_bust(info.context.user)
        all_orgs = Organization.objects.qs.editable_by_user(user)
        depth += 1
        if plan:
            plan_obj = Plan.objects.qs.visible_for_user(user).by_id_or_identifier(plan).first()
            if not plan_obj:
                raise ValueError(f'Plan with identifier {plan} not found')
            all_orgs = all_orgs.available_for_plan(plan_obj)
        if parent:
            parent_org = all_orgs.filter(pk=parent).first()
            if not parent_org:
                raise ValueError(f'Organization with ID {parent} not found')
            all_orgs = all_orgs.filter(path__startswith=parent_org.path).exclude(pk=parent_org.pk)
            depth += parent_org.depth
        all_orgs = all_orgs.filter(depth__lte=depth)
        if contains:
            all_orgs = all_orgs.filter(name__icontains=contains)
        return all_orgs.order_by('path')

    @strawberry_django.field(
        description='Get actions by their IDs', graphql_type=list[Annotated['ActionNode', sb.lazy('.schema')]]
    )
    def actions(
        self,
        info: SBInfo,
        ids: Annotated[list[sb.ID], 'List of action IDs to fetch'],
    ) -> Iterable[Action]:
        user = user_or_bust(info.context.user)
        return Action.objects.qs.visible_for_user(user).filter(pk__in=ids)
