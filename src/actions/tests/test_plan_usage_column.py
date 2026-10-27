"""
Tests for the superuser-only Usage column in the Plans admin listing.

The column surfaces Plan.usage_status compactly: a short per-value label (with the full label
on hover), a blank cell for the ordinary customer-use default, and it is shown only to
superusers (like the Clients column).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from actions.models.plan import UsageStatus
from actions.tests.factories import PlanFactory
from actions.tests.test_change_log_graphql import make_plan_admin

if TYPE_CHECKING:
    from actions.models import Plan

pytestmark = pytest.mark.django_db


def _list_url() -> str:
    return reverse('wagtailsnippets_actions_plan:list')


def _render(client, plan: Plan, *, superuser: bool) -> str:
    user = make_plan_admin(plan)
    if superuser:
        user.is_superuser = True
        user.save(update_fields=['is_superuser'])
    client.force_login(user)
    return client.get(_list_url()).content.decode()


class TestUsageColumn:
    def test_superuser_sees_short_label_and_full_label_tooltip(self, client):
        plan = PlanFactory.create(usage_status=UsageStatus.DEVELOPMENT)
        content = _render(client, plan, superuser=True)

        assert 'kw-scroll-table' in content  # the listing rendered
        assert 'kw-col-plan-usage' in content  # the column is present
        assert 'class="plan-usage"' in content  # the value span was rendered
        assert 'Dev / test' in content  # the short label
        assert str(UsageStatus.DEVELOPMENT.label) in content  # full label as hover tooltip

    def test_customer_use_default_renders_a_blank_cell(self, client):
        plan = PlanFactory.create(usage_status=UsageStatus.CUSTOMER_USE)
        content = _render(client, plan, superuser=True)

        assert 'kw-col-plan-usage' in content  # column header still shown
        assert 'class="plan-usage"' not in content  # but no value span for the default

    def test_column_hidden_from_non_superusers(self, client):
        plan = PlanFactory.create(usage_status=UsageStatus.DEPRECATED)
        content = _render(client, plan, superuser=False)

        assert 'kw-scroll-table' in content  # the listing rendered for the plan admin
        assert 'kw-col-plan-usage' not in content  # superuser-only column is absent
        assert 'Deprecated' not in content
