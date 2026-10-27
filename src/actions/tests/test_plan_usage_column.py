"""
Tests for the superuser-only Usage column in the Plans admin listing.

The column surfaces Plan.usage_status compactly: a short per-value label (with the full label
on hover), a blank cell for the ordinary customer-use default, and it is shown only to
superusers (like the Clients column).
"""

from __future__ import annotations

from importlib import import_module

from django.apps import apps as global_apps
from django.urls import reverse

import pytest

from actions.models import Plan
from actions.models.plan import UsageStatus
from actions.tests.factories import PlanFactory
from actions.tests.test_change_log_graphql import make_plan_admin

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

    def test_not_in_use_status_renders_its_short_label(self, client):
        # The usage status formerly named "inactive" was renamed to "not in use" to avoid
        # colliding with the separate plan is_active concept.
        plan = PlanFactory.create(usage_status=UsageStatus.NOT_IN_USE)
        content = _render(client, plan, superuser=True)

        assert 'class="plan-usage"' in content
        assert 'Not in use' in content


class TestUsageStatusRenameMigration:
    def test_forward_converts_inactive_to_not_in_use(self):
        migration = import_module('actions.migrations.0203_rename_inactive_usage_status')
        plan = PlanFactory.create()
        # Write the legacy raw value directly (it is no longer a valid choice).
        Plan.objects.filter(pk=plan.pk).update(usage_status='inactive')

        migration.rename_inactive_to_not_in_use(global_apps, None)

        plan.refresh_from_db()
        assert plan.usage_status == UsageStatus.NOT_IN_USE

    def test_other_usage_statuses_are_left_untouched(self):
        migration = import_module('actions.migrations.0203_rename_inactive_usage_status')
        sales = PlanFactory.create(usage_status=UsageStatus.SALES)
        customer = PlanFactory.create(usage_status=UsageStatus.CUSTOMER_USE)

        migration.rename_inactive_to_not_in_use(global_apps, None)

        sales.refresh_from_db()
        customer.refresh_from_db()
        assert sales.usage_status == UsageStatus.SALES
        assert customer.usage_status == UsageStatus.CUSTOMER_USE
