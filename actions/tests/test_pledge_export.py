from __future__ import annotations

import csv
import io
from typing import TYPE_CHECKING

from django.db.models import Count

import pytest

from actions.models import Pledge, PledgeCommitment, PledgeUser
from actions.pledge_admin import PledgeIndexView, PledgeViewSet
from actions.tests.factories import PlanFactory, PledgeFactory

if TYPE_CHECKING:
    from django.test import RequestFactory

    from users.models import User

pytestmark = pytest.mark.django_db


def _get_view_and_queryset(rf: RequestFactory, user: User, plan):
    """Set up a PledgeIndexView and build the queryset for the given plan."""
    view_set = PledgeViewSet()
    view = PledgeIndexView(
        **view_set.get_common_view_kwargs(),
        **view_set.get_index_view_kwargs(),
    )
    request = rf.get('/admin/', {'export': 'csv'})
    request.user = user
    view.setup(request)
    view.filterset_class = None  # type: ignore[assignment]
    queryset = Pledge.objects.filter(plan=plan).annotate(commitment_count=Count('commitments'))
    return view, queryset


def _parse_csv_rows(view: PledgeIndexView, queryset) -> list[dict[str, str]]:
    """Stream CSV from the view and parse into a list of row dicts."""
    raw = b''.join(view.stream_csv(queryset))
    reader = csv.DictReader(io.StringIO(raw.decode('utf-8')))
    return list(reader)


class TestPledgeExportCSV:
    @pytest.fixture(autouse=True)
    def setup(self, plan_admin_user):
        self.user = plan_admin_user
        self.plan = self.user.get_active_admin_plan()
        self.plan.features.enable_community_engagement = True
        self.plan.features.save()

    def test_basic_export_columns(self, rf):
        """Export should contain the base columns: ID, Name, Slug, Number of commitments."""
        PledgeFactory.create(plan=self.plan)

        view, qs = _get_view_and_queryset(rf, self.user, self.plan)
        rows = _parse_csv_rows(view, qs)

        assert len(rows) == 1
        row = rows[0]
        assert set(row.keys()) >= {'ID', 'Name', 'Slug', 'Number of commitments'}

    def test_commitment_count(self, rf):
        """Export should reflect the correct number of commitments per pledge."""
        pledge = PledgeFactory.create(plan=self.plan)
        for _ in range(3):
            PledgeCommitment.objects.create(
                pledge=pledge,
                pledge_user=PledgeUser.objects.create(),
            )

        view, qs = _get_view_and_queryset(rf, self.user, self.plan)
        rows = _parse_csv_rows(view, qs)

        assert rows[0]['Number of commitments'] == '3'

    def test_user_data_columns(self, rf):
        """User data keys from commitments should appear as extra columns."""
        pledge = PledgeFactory.create(plan=self.plan)
        PledgeCommitment.objects.create(
            pledge=pledge,
            pledge_user=PledgeUser.objects.create(user_data={'zip_code': '00100', 'city': 'Helsinki'}),
        )
        PledgeCommitment.objects.create(
            pledge=pledge,
            pledge_user=PledgeUser.objects.create(user_data={'zip_code': '00200'}),
        )

        view, qs = _get_view_and_queryset(rf, self.user, self.plan)
        rows = _parse_csv_rows(view, qs)

        row = rows[0]
        assert row['zip_code'] == '00100, 00200'
        assert row['city'] == 'Helsinki'

    def test_multiple_pledges(self, rf):
        """Export should include one row per pledge."""
        PledgeFactory.create(plan=self.plan, name='First Pledge')
        PledgeFactory.create(plan=self.plan, name='Second Pledge')

        view, qs = _get_view_and_queryset(rf, self.user, self.plan)
        rows = _parse_csv_rows(view, qs)

        names = {row['Name'] for row in rows}
        assert names == {'First Pledge', 'Second Pledge'}

    def test_only_own_plan_pledges(self, rf):
        """Export should only include pledges from the user's active plan."""
        PledgeFactory.create(plan=self.plan, name='My Pledge')

        other_plan = PlanFactory.create()
        other_plan.features.enable_community_engagement = True
        other_plan.features.save()
        PledgeFactory.create(plan=other_plan, name='Other Pledge')

        view, qs = _get_view_and_queryset(rf, self.user, self.plan)
        rows = _parse_csv_rows(view, qs)

        names = {row['Name'] for row in rows}
        assert 'My Pledge' in names
        assert 'Other Pledge' not in names

    def test_comma_in_user_data_value(self, rf):
        """Values containing commas should be properly handled in CSV."""
        pledge = PledgeFactory.create(plan=self.plan)
        PledgeCommitment.objects.create(
            pledge=pledge,
            pledge_user=PledgeUser.objects.create(user_data={'location': 'City, State'}),
        )

        view, qs = _get_view_and_queryset(rf, self.user, self.plan)
        rows = _parse_csv_rows(view, qs)

        assert rows[0]['location'] == 'City, State'
