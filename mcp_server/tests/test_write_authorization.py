from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING, cast

from django.utils import timezone

import pytest
from asgiref.sync import async_to_sync
from fastmcp.exceptions import ToolError
from fastmcp.server.elicitation import AcceptedElicitation
from mcp.server.elicitation import CancelledElicitation, DeclinedElicitation

from actions.tests.factories import PlanFactory
from mcp_server.tools import helpers
from mcp_server.tools import plan as plan_tools
from users.models import MCPPlanWriteAuthorizationGrant
from users.tests.factories import UserFactory

if TYPE_CHECKING:
    from fastmcp import Context

pytestmark = pytest.mark.django_db


class FakeContext:
    def __init__(self, result):
        self.result = result
        self.calls = 0

    async def elicit(self, _message: str, _choices: list[str]):
        self.calls += 1
        return self.result


class FailingContext:
    async def elicit(self, _message: str, _choices: list[str]):
        raise AssertionError('elicit should not be called')


def test_existing_active_grant_skips_elicitation(monkeypatch):
    user = UserFactory.create(is_superuser=True)
    plan = PlanFactory.create()
    MCPPlanWriteAuthorizationGrant.objects.create(
        user=user,
        plan=plan,
        expires_at=timezone.now() + timedelta(hours=1),
        granted_by_tool='preexisting',
    )

    monkeypatch.setattr(helpers, 'resolve_current_user', lambda: user)
    async_to_sync(helpers.require_mcp_plan_write_authorization)(
        plan_ref=str(plan.id),
        tool_name='update_action',
        ctx=cast('Context', FailingContext()),
    )


def test_missing_grant_prompts_and_persists_authorization(monkeypatch):
    user = UserFactory.create(is_superuser=True)
    plan = PlanFactory.create()
    monkeypatch.setattr(helpers, 'resolve_current_user', lambda: user)
    ctx = FakeContext(AcceptedElicitation[str](data='1h'))

    async_to_sync(helpers.require_mcp_plan_write_authorization)(
        plan_ref=str(plan.id),
        tool_name='update_action',
        ctx=cast('Context', ctx),
    )

    grant = MCPPlanWriteAuthorizationGrant.objects.get(user=user, plan=plan)
    assert grant.expires_at > timezone.now()
    assert grant.granted_by_tool == 'update_action'
    assert ctx.calls == 1


@pytest.mark.parametrize('result', [DeclinedElicitation(), CancelledElicitation()])
def test_declined_or_cancelled_elicitation_blocks_write(monkeypatch, result):
    user = UserFactory.create(is_superuser=True)
    plan = PlanFactory.create()
    monkeypatch.setattr(helpers, 'resolve_current_user', lambda: user)
    ctx = FakeContext(result)

    with pytest.raises(ToolError, match='was not granted'):
        async_to_sync(helpers.require_mcp_plan_write_authorization)(
            plan_ref=str(plan.id),
            tool_name='update_action',
            ctx=cast('Context', ctx),
        )
    assert not MCPPlanWriteAuthorizationGrant.objects.filter(user=user, plan=plan).exists()


def test_grants_are_scoped_by_user_and_plan(monkeypatch):
    user = UserFactory.create(is_superuser=True)
    other_user = UserFactory.create(is_superuser=True)
    plan = PlanFactory.create()
    MCPPlanWriteAuthorizationGrant.objects.create(
        user=other_user,
        plan=plan,
        expires_at=timezone.now() + timedelta(hours=1),
        granted_by_tool='other_user',
    )

    monkeypatch.setattr(helpers, 'resolve_current_user', lambda: user)
    ctx = FakeContext(AcceptedElicitation[str](data='15m'))
    async_to_sync(helpers.require_mcp_plan_write_authorization)(
        plan_ref=str(plan.id),
        tool_name='create_category_type',
        ctx=cast('Context', ctx),
    )

    assert MCPPlanWriteAuthorizationGrant.objects.filter(user=user, plan=plan).exists()
    assert ctx.calls == 1


def test_authorize_plan_edits_requires_explicit_elicitation(monkeypatch):
    user = UserFactory.create(is_superuser=True)
    plan = PlanFactory.create()
    monkeypatch.setattr(helpers, 'resolve_current_user', lambda: user)
    ctx = FakeContext(AcceptedElicitation[str](data='24h'))

    result = async_to_sync(plan_tools.authorize_plan_edits)(
        plan_id=str(plan.id),
        duration='24h',
        ctx=cast('Context', ctx),
    )

    grant = MCPPlanWriteAuthorizationGrant.objects.get(user=user, plan=plan)
    assert ctx.calls == 1
    assert grant.granted_by_tool == 'authorize_plan_edits'
    assert "Write access authorized for plan" in result


def test_authorize_plan_edits_decline_does_not_create_grant(monkeypatch):
    user = UserFactory.create(is_superuser=True)
    plan = PlanFactory.create()
    monkeypatch.setattr(helpers, 'resolve_current_user', lambda: user)
    ctx = FakeContext(DeclinedElicitation())

    with pytest.raises(ToolError, match='was not granted'):
        async_to_sync(plan_tools.authorize_plan_edits)(
            plan_id=str(plan.id),
            duration='1h',
            ctx=cast('Context', ctx),
        )

    assert not MCPPlanWriteAuthorizationGrant.objects.filter(user=user, plan=plan).exists()
