"""The indicators sheet of the report export, and the freezing of indicator data with action and report completion."""

from __future__ import annotations

import datetime
import io
from typing import Any

from django.utils.translation import gettext as _, pgettext

import pytest
from openpyxl import load_workbook

from actions.tests.factories import ActionFactory, PlanFactory
from indicators.tests.factories import (
    ActionIndicatorFactory,
    DimensionCategoryFactory,
    IndicatorFactory,
    IndicatorGoalFactory,
    IndicatorValueFactory,
)
from reports.export import export_dashboard_report_for_plan
from reports.models import IndicatorSnapshot

from .fixtures import *

pytestmark = pytest.mark.django_db


def _rows(report, user) -> dict[str, dict[str, Any]]:
    df = report.get_xlsx_exporter(user=user).generate_indicators_dataframe()
    return {row[_('Indicator')]: row for row in df.iter_rows(named=True)}


@pytest.fixture
def report(plan, report_factory, report_type_factory):
    # The report period starts 2023-12-15
    return report_factory(type=report_type_factory(plan=plan))


@pytest.fixture
def indicator(plan, action):
    indicator = IndicatorFactory.create(plans=[plan], name='Emissions')
    ActionIndicatorFactory.create(action=action, indicator=indicator)
    return indicator


def test_live_data(plan, action, superuser, report, indicator):
    IndicatorValueFactory.create(indicator=indicator, date=datetime.date(2022, 12, 31), value=10.0)
    IndicatorValueFactory.create(indicator=indicator, date=datetime.date(2023, 12, 31), value=8.0)
    IndicatorValueFactory.create(indicator=indicator, date=datetime.date(2024, 12, 31), value=6.0)
    IndicatorValueFactory.create(
        indicator=indicator, date=datetime.date(2025, 12, 31), value=99.0, categories=[DimensionCategoryFactory.create()]
    )
    IndicatorGoalFactory.create(indicator=indicator, date=datetime.date(2030, 12, 31), value=2.0)
    IndicatorGoalFactory.create(indicator=indicator, date=datetime.date(2035, 12, 31), value=0.0)
    IndicatorFactory.create(plans=[plan], name='Unlinked')

    rows = _rows(report, superuser)

    row = rows['Emissions']
    assert row[_('Unit')] == str(indicator.unit)
    assert row[_('Organization')] == str(indicator.organization)
    assert row[_('Value at start of reporting period')] == 10.0
    assert row[_('Date of value at start of reporting period')] == datetime.date(2022, 12, 31)
    assert row[_('Latest value')] == 6.0
    assert row[_('Date of latest value')] == datetime.date(2024, 12, 31)
    assert row[_('Target value')] == 0.0
    assert row[_('Target date')] == datetime.date(2035, 12, 31)
    assert action.identifier in row[pgettext('Action model', 'Actions')]
    assert rows['Unlinked'][pgettext('Action model', 'Actions')] == ''
    assert _('Data frozen at') not in next(iter(rows.values()))


def test_action_completion_freezes_its_indicators(plan, action, superuser, report, indicator):
    value = IndicatorValueFactory.create(indicator=indicator, date=datetime.date(2024, 12, 31), value=6.0)
    unlinked = IndicatorFactory.create(plans=[plan], name='Unlinked')
    unlinked_value = IndicatorValueFactory.create(indicator=unlinked, date=datetime.date(2024, 12, 31), value=1.0)

    action.mark_as_complete_for_report(report, superuser)
    value.value = 7.0
    value.save()
    unlinked_value.value = 2.0
    unlinked_value.save()

    rows = _rows(report, superuser)
    assert rows['Emissions'][_('Latest value')] == 6.0
    assert rows['Emissions'][_('Data frozen at')] is not None
    assert rows['Unlinked'][_('Latest value')] == 2.0
    assert rows['Unlinked'][_('Data frozen at')] is None


def test_latest_action_completion_wins(plan, action, superuser, report, indicator):
    other_action = ActionFactory.create(plan=plan)
    ActionIndicatorFactory.create(action=other_action, indicator=indicator)
    value = IndicatorValueFactory.create(indicator=indicator, date=datetime.date(2024, 12, 31), value=6.0)

    action.mark_as_complete_for_report(report, superuser)
    value.value = 7.0
    value.save()
    other_action.mark_as_complete_for_report(report, superuser)
    value.value = 8.0
    value.save()

    assert _rows(report, superuser)['Emissions'][_('Latest value')] == 7.0


def test_undoing_action_completion_keeps_snapshots_of_other_complete_actions(plan, action, superuser, report, indicator):
    other_action = ActionFactory.create(plan=plan)
    ActionIndicatorFactory.create(action=other_action, indicator=indicator)
    only_linked_to_action = IndicatorFactory.create(plans=[plan])
    ActionIndicatorFactory.create(action=action, indicator=only_linked_to_action)

    action.mark_as_complete_for_report(report, superuser)
    other_action.mark_as_complete_for_report(report, superuser)
    action.undo_marking_as_complete_for_report(report, superuser)

    assert set(report.indicator_snapshots.values_list('indicator', flat=True)) == {indicator.pk}


def test_report_completion_freezes_remaining_indicators(plan, action, superuser, report, indicator):
    unlinked = IndicatorFactory.create(plans=[plan], name='Unlinked')
    value = IndicatorValueFactory.create(indicator=unlinked, date=datetime.date(2024, 12, 31), value=1.0)
    IndicatorFactory.create(name='Other plan', plans=[PlanFactory.create()])
    action.mark_as_complete_for_report(report, superuser)

    report.mark_as_complete(superuser)
    value.value = 2.0
    value.save()
    IndicatorFactory.create(plans=[plan], name='Added after completion')

    rows = _rows(report, superuser)
    assert set(rows) == {'Emissions', 'Unlinked'}
    assert rows['Unlinked'][_('Latest value')] == 1.0

    report.undo_marking_as_complete(superuser)
    assert list(IndicatorSnapshot.objects.filter(report=report).values_list('indicator', flat=True)) == [indicator.pk]


@pytest.mark.usefixtures('indicator')
def test_internal_indicators_are_hidden_from_anonymous_users(plan, superuser, report):
    IndicatorFactory.create(plans=[plan], name='Internal', visibility='internal')

    assert set(_rows(report, None)) == {'Emissions'}
    assert set(_rows(report, superuser)) == {'Emissions', 'Internal'}


@pytest.mark.usefixtures('indicator')
def test_sheet_is_only_in_report_export(plan_with_pages, superuser, report):
    report_output = report.get_xlsx_exporter(user=superuser).generate_xlsx()
    dashboard_output, _filename = export_dashboard_report_for_plan(plan_with_pages, 'xlsx', superuser)
    assert isinstance(dashboard_output, bytes)

    assert _('Indicators') in load_workbook(io.BytesIO(report_output), read_only=True).sheetnames
    assert _('Indicators') not in load_workbook(io.BytesIO(dashboard_output), read_only=True).sheetnames
