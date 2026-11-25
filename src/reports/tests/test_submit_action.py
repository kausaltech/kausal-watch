"""Editors submit an action to a report from its menu, after a confirmation of what the submission captures."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

from django.contrib.messages import get_messages
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

import pytest

from aplans.cache import PlanSpecificCache

from actions.schema import ActionNode
from actions.tests import action_admin_helpers as h
from actions.tests.factories import WorkflowFactory
from admin_site.tests.factories import ClientPlanFactory
from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory, IndicatorValueFactory
from reports.models import ActionSnapshot, IndicatorSnapshot
from reports.tests.factories import ReportFactory, ReportTypeFactory

if TYPE_CHECKING:
    from kausal_common.graphene import GQLInfo

pytestmark = pytest.mark.django_db


def _resubmit_url(action, report_pk) -> str:
    return reverse('wagtailsnippets_actions_action:resubmit_action_for_report', args=(action.pk, report_pk))


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


def test_action_menu_offers_resubmitting_a_submission(rf, plan_admin_user, action, report):
    """Undoing the submission is offered in the report's list of submissions instead."""
    action.mark_as_complete_for_report(report, plan_admin_user)
    submitted_on = date_format(timezone.localtime(action.submitted_at_for_report(report)), 'SHORT_DATE_FORMAT')
    [resubmit] = _reporting_buttons(rf, plan_admin_user, action)
    assert resubmit.label == f'Resubmit for Quarterly report • Q3 2026 (submitted {submitted_on})'
    assert resubmit.url == _resubmit_url(action, report.pk)


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


def test_resubmission_replaces_the_submission_with_the_current_data(plan_admin_user, action, report):
    indicator = _linked_indicator(action, 'Total emissions', value=10)
    action.mark_as_complete_for_report(report, plan_admin_user)

    action.name = 'Renamed since submitting'
    action.save()
    indicator.latest_value = IndicatorValueFactory.create(indicator=indicator, value=20, date='2026-06-30')
    indicator.save(update_fields=['latest_value'])
    action.resubmit_for_report(report, plan_admin_user)

    snapshot = ActionSnapshot.objects.get(report=report)
    assert snapshot.action_version.field_dict['name'] == 'Renamed since submitting'
    # Freezing skips indicators that already have a snapshot, so check the old one was replaced
    [indicator_snapshot] = IndicatorSnapshot.objects.filter(report=report, action=action)
    assert indicator_snapshot.data['latest_value']['value'] == 20


def test_resubmitting_needs_an_earlier_submission(plan_admin_user, action, report):
    with pytest.raises(ValueError, match='has not been submitted'):
        action.resubmit_for_report(report, plan_admin_user)
    assert not ActionSnapshot.objects.filter(report=report).exists()


def test_resubmitting_to_a_completed_report_keeps_the_submission(plan_admin_user, action, report):
    action.mark_as_complete_for_report(report, plan_admin_user)
    snapshot = ActionSnapshot.objects.get(report=report)
    report.mark_as_complete(plan_admin_user)

    with pytest.raises(ValueError, match='already marked as complete'):
        action.resubmit_for_report(report, plan_admin_user)
    assert ActionSnapshot.objects.get(report=report) == snapshot


def test_resubmit_confirmation_names_the_submission_it_replaces(admin_client, plan_admin_user, action, report):
    action.mark_as_complete_for_report(report, plan_admin_user)
    submitted_on = date_format(timezone.localtime(action.submitted_at_for_report(report)), 'DATE_FORMAT')
    content = admin_client.get(_resubmit_url(action, report.pk)).content.decode()
    assert f'This replaces its submission from {submitted_on} with the current data of the action.' in content
    assert 'value="Resubmit"' in content


def test_resubmitting_confirms_in_a_message(admin_client, plan_admin_user, action, report):
    action.mark_as_complete_for_report(report, plan_admin_user)
    response = admin_client.post(_resubmit_url(action, report.pk))
    assert _messages(response) == [f"Action '{action}' has been resubmitted to the report 'Quarterly report • Q3 2026'."]
    assert ActionSnapshot.objects.filter(report=report).count() == 1
