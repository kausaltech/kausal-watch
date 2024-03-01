import pytest
import reversion
import typing
from reversion.models import Version, Revision

from actions.models import Action
from reports.models import Report, ActionSnapshot, SerializedActionVersion
from .fixtures import *  # noqa


pytestmark = pytest.mark.django_db


@pytest.fixture
def report_type_with_multiple_reports(plan, report_type_factory, report_factory):
    rt = report_type_factory(plan=plan)
    report_factory(type=rt, name='Report 1')
    report_factory(type=rt, name='Report 2')
    report_factory(type=rt, name='Report 3')
    return rt


@pytest.fixture
def plan_with_some_actions(plan, action_factory):
    for _ in range(0, 9):
        action_factory(plan=plan)
    return plan


def test_report_action_snapshots(plan_with_some_actions, report_type_with_multiple_reports, user):
    """ This test intentionally creates revisions sequentially
    to test that the correct revisions / versions get tied to
    the actions when reporting / completing
    """
    actions = plan_with_some_actions.actions.all()

    #action_ct = ContentType.objects.get_for_model(Action)

    # Step 0: add revision+versions without any report / snapshot connection
    assert Revision.objects.count() == 0

    NON_REPORT_REVISION = "Non-report revision"

    with reversion.create_revision():
        reversion.set_comment(NON_REPORT_REVISION)
        for action in actions:
            reversion.add_to_revision(action)

    assert Revision.objects.count() == 1
    assert Version.objects.get_for_model(Action).count() == 9
    revision_without_snapshot = Version.objects.first().revision
    assert revision_without_snapshot.get_comment() == NON_REPORT_REVISION

    for action in actions:
        version = Version.objects.get_for_object(action).get()
        assert version.revision == revision_without_snapshot

    # Step 1: Mark whole report 1 complete
    report_complete = Report.objects.get(name='Report 1')
    report_complete.mark_as_complete(user)

    assert Revision.objects.count() == 2
    assert ActionSnapshot.objects.count() == 9
    assert Version.objects.get_for_model(Action).count() == 18
    revision_for_complete_report = Version.objects.first().revision
    assert revision_for_complete_report != revision_without_snapshot

    actions_by_pk = {a.pk: a for a in actions}

    for action in actions:
        version = Version.objects.get_for_object(action).first()
        assert version.revision == revision_for_complete_report, version.revision.get_comment()
        actions_by_pk[action.pk].__version = version

    snapshots = report_complete.action_snapshots.all()
    for snapshot in snapshots:
        action_pk = snapshot.action_version.object_id
        assert actions_by_pk[int(action_pk)].__version == snapshot.action_version

    # Step 2: Mark some actions for partial report 2 complete
    report_partially_complete = Report.objects.get(name='Report 2')
    report_partially_complete = typing.cast(Report, report_partially_complete)
    complete_actions = actions[0:3]
    for action in complete_actions:
        action.mark_as_complete_for_report(report_partially_complete, user)

    assert Revision.objects.count() == 2 + 3  # One extra revision per completed action

    for action in actions:
        version = Version.objects.get_for_object(action).first()
        actions_by_pk[action.pk].__version = version

    live_versions = report_partially_complete.get_live_versions()
    for action_version in live_versions.actions:
        pk = action_version.field_dict['id']
        assert isinstance(pk, int)
        if pk in [a.pk for a in complete_actions]:
            assert action_version.pk is not None
            pk = action_version.field_dict['id']
            assert actions_by_pk[pk].__version == action_version
        else:
            assert action_version.pk is None

    for action in actions:
        version = Version.objects.get_for_object(action).first()
        revision = version.revision
        if action in complete_actions:
            assert revision != revision_for_complete_report
            assert revision != revision_without_snapshot
        else:
            assert revision == revision_for_complete_report

    # Step 3: Test that the completely incomplete report doesn't
    # get the previous existing versions
    report_incomplete = Report.objects.get(name='Report 3')
    report_incomplete = typing.cast(Report, report_incomplete)

    live_versions = report_incomplete.get_live_versions()
    for action_version in live_versions.actions:
        assert SerializedActionVersion.from_version(action_version).completed_at is None
        assert action_version.pk is None
        pk = action_version.field_dict['id']
        assert actions_by_pk[pk].__version != action_version

    assert Revision.objects.count() == 2 + 3
