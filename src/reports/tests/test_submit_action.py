"""Editors submit an action to a report from its menu, after a confirmation of what the submission captures."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from django.contrib.messages import get_messages

import pytest

from aplans.cache import PlanSpecificCache

from actions.schema import ActionNode
from actions.tests import action_admin_helpers as h
from actions.tests.factories import WorkflowFactory
from admin_site.tests.factories import ClientPlanFactory
from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory, IndicatorValueFactory
from reports.models import ActionSnapshot
from reports.tests.factories import ReportFactory, ReportTypeFactory

if TYPE_CHECKING:
    from kausal_common.graphene import GQLInfo

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def report(plan_with_pages):
    report_type = ReportTypeFactory.create(plan=plan_with_pages, name='Quarterly report')
    return ReportFactory.create(type=report_type, name='Q3 2026')


def _reporting_buttons(rf, user, action) -> list[Any]:
    """Return the action's menu items in the reporting section, as the action list's GraphQL field returns them."""
    request = rf.get('/admin/')
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=action.plan)
    buttons = ActionNode.resolve_admin_buttons(action, cast('GQLInfo', SimpleNamespace(context=request)))
    return [button for button in buttons if getattr(button, 'section', None)]


def _moderate(plan) -> None:
    plan.features.moderation_workflow = WorkflowFactory.create()
    plan.features.save(update_fields=['moderation_workflow'])


def _linked_indicator(action, name, value=None):
    indicator = IndicatorFactory.create(name=name, plans=[action.plan])
    ActionIndicatorFactory.create(action=action, indicator=indicator)
    if value is not None:
        indicator.latest_value = IndicatorValueFactory.create(indicator=indicator, value=value)
        indicator.save(update_fields=['latest_value'])
    return indicator


def test_action_menu_offers_submitting_in_a_reporting_section(rf, plan_admin_user, action, report):
    [button] = _reporting_buttons(rf, plan_admin_user, action)
    assert button.label == 'Submit for Quarterly report • Q3 2026'
    assert button.section == 'Reporting'
    assert button.url == h.mark_as_complete_url(action, report.pk)


def test_action_menu_offers_undoing_a_submission(rf, plan_admin_user, action, report):
    action.mark_as_complete_for_report(report, plan_admin_user)
    [button] = _reporting_buttons(rf, plan_admin_user, action)
    assert button.label == 'Undo submission for Quarterly report • Q3 2026'
    assert button.url == h.undo_marking_as_complete_url(action, report.pk)


def test_confirmation_lists_the_indicators_the_submission_captures(admin_client, action, report):
    _linked_indicator(action, 'Total emissions', value=4820)
    _linked_indicator(action, 'Energy use')
    content = admin_client.get(h.mark_as_complete_url(action, report.pk)).content.decode()
    assert 'Quarterly report • Q3 2026' in content
    assert 'Total emissions' in content
    assert 'Current: 4820' in content
    assert 'Energy use' in content
    assert 'No values yet' in content


def test_confirmation_without_indicators_lists_none(admin_client, action, report):
    content = admin_client.get(h.mark_as_complete_url(action, report.pk)).content.decode()
    assert 'submitted-indicators' not in content


def test_confirmation_warns_about_unpublished_changes_on_moderated_plan(admin_client, plan_admin_user, action, report):
    _moderate(action.plan)
    action.name = 'Draft name'
    action.save_revision(user=plan_admin_user)
    content = admin_client.get(h.mark_as_complete_url(action, report.pk)).content.decode()
    assert 'changes that have not been published yet' in content


def test_confirmation_has_no_warning_without_unpublished_changes(admin_client, action, report):
    _moderate(action.plan)
    content = admin_client.get(h.mark_as_complete_url(action, report.pk)).content.decode()
    assert 'changes that have not been published yet' not in content


def test_submission_captures_the_published_version_of_a_moderated_action(admin_client, plan_admin_user, action, report):
    """The warning's promise: a draft waiting for approval stays out of the report."""
    _moderate(action.plan)
    published_name = action.name
    action.name = 'Draft name'
    action.save_revision(user=plan_admin_user)

    response = admin_client.post(h.mark_as_complete_url(action, report.pk))
    assert response.status_code == 302
    snapshot = ActionSnapshot.objects.get(report=report)
    assert snapshot.action_version.field_dict['name'] == published_name


def _messages(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


def test_submitting_and_undoing_confirm_in_the_new_words(admin_client, action, report):
    response = admin_client.post(h.mark_as_complete_url(action, report.pk))
    assert _messages(response) == [f"Action '{action}' has been submitted to the report 'Quarterly report • Q3 2026'."]

    response = admin_client.post(h.undo_marking_as_complete_url(action, report.pk))
    # The first message is still queued: no page has shown it in between
    assert _messages(response)[-1] == (
        f"The submission of action '{action}' to the report 'Quarterly report • Q3 2026' has been undone."
    )
    assert not ActionSnapshot.objects.filter(report=report).exists()
