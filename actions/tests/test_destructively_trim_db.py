from wagtail.models import Revision

import pytest

from actions.management.commands.destructively_trim_db import Command
from actions.tests.factories import ActionFactory

pytestmark = pytest.mark.django_db


def test_delete_userless_wagtail_revisions_keeps_existing_drafts():
    action = ActionFactory.create()
    revision = action.save_revision(user=None)

    Command().delete_userless_wagtail_revisions()

    action.refresh_from_db()
    assert action.latest_revision_id == revision.id
    assert Revision.objects.filter(id=revision.id).exists()


def test_delete_userless_wagtail_revisions_deletes_orphaned_drafts():
    action = ActionFactory.create()
    revision = action.save_revision(user=None)
    action.delete()

    Command().delete_userless_wagtail_revisions()

    assert not Revision.objects.filter(id=revision.id).exists()
