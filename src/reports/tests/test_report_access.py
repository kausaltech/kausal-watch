"""Report admin views only act on reports of plans the user administers."""

from __future__ import annotations

from django.urls import reverse

import pytest

from actions.tests.factories import PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from reports.tests.factories import ReportFactory, ReportTypeFactory
from reports.views import MarkReportAsCompleteView
from reports.wagtail_admin import ReportAdmin

from .fixtures import *

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def own_report(plan_with_pages):
    return ReportFactory.create(type=ReportTypeFactory.create(plan=plan_with_pages))


@pytest.fixture
def other_plan_report():
    return ReportFactory.create(type=ReportTypeFactory.create(plan=PlanFactory.create()))


def _download_url(report) -> str:
    return reverse(ReportAdmin().url_helper.get_action_url_name('download'), kwargs={'instance_pk': report.pk})


def test_admin_can_download_report_of_own_plan(admin_client, own_report):
    assert admin_client.get(_download_url(own_report)).status_code == 200


def test_admin_cannot_download_report_of_another_plan(admin_client, other_plan_report):
    assert admin_client.get(_download_url(other_plan_report)).status_code == 404


def _mark_report_view(report) -> MarkReportAsCompleteView:
    view = MarkReportAsCompleteView.__new__(MarkReportAsCompleteView)
    view.report = report
    return view


def test_admin_may_mark_report_of_own_plan_complete(plan_admin_user, own_report):
    assert _mark_report_view(own_report).check_action_permitted(plan_admin_user)


def test_admin_may_not_mark_report_of_another_plan_complete(plan_admin_user, other_plan_report):
    assert not _mark_report_view(other_plan_report).check_action_permitted(plan_admin_user)
