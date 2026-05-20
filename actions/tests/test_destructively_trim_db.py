from unittest.mock import call, patch

import reversion
from reversion.models import Revision as ReversionRevision, Version
from wagtail.models import Revision

import pytest

from actions.management.commands.destructively_trim_db import Command
from actions.tests.factories import ActionFactory
from pages.tests.factories import CategoryTypePageFactory, StaticPageFactory

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


def test_delete_userless_wagtail_revisions_handles_page_subclasses(plan_with_pages):
    page = StaticPageFactory.create(parent=plan_with_pages.root_page)
    revision = page.save_revision(user=None)

    Command().delete_userless_wagtail_revisions()

    page.refresh_from_db()
    assert page.latest_revision_id == revision.id
    assert Revision.objects.filter(id=revision.id).exists()


def test_delete_userless_wagtail_revisions_handles_multi_table_page_subclasses(plan_with_pages, category_type):
    page = CategoryTypePageFactory.create(parent=plan_with_pages.root_page, category_type=category_type)
    revision = page.save_revision(user=None)

    Command().delete_userless_wagtail_revisions()

    page.refresh_from_db()
    assert page.latest_revision_id == revision.id
    assert Revision.objects.filter(id=revision.id).exists()


def test_delete_userless_reversion_revisions_keeps_existing_objects():
    action = ActionFactory.create()
    with reversion.create_revision():
        reversion.add_to_revision(action)

    revision = ReversionRevision.objects.get()

    Command().delete_userless_reversion_revisions()

    assert ReversionRevision.objects.filter(id=revision.id).exists()
    assert Version.objects.filter(revision_id=revision.id, object_id=str(action.pk)).exists()


def test_delete_userless_reversion_revisions_keeps_revision_if_any_version_still_exists():
    kept_action = ActionFactory.create()
    deleted_action = ActionFactory.create(plan=kept_action.plan)
    with reversion.create_revision():
        reversion.add_to_revision(kept_action)
        reversion.add_to_revision(deleted_action)

    revision = ReversionRevision.objects.get()
    deleted_action.delete()

    Command().delete_userless_reversion_revisions()

    assert ReversionRevision.objects.filter(id=revision.id).exists()


def test_delete_userless_reversion_revisions_deletes_orphaned_objects():
    action = ActionFactory.create()
    with reversion.create_revision():
        reversion.add_to_revision(action)

    revision = ReversionRevision.objects.get()
    action.delete()

    Command().delete_userless_reversion_revisions()

    assert not ReversionRevision.objects.filter(id=revision.id).exists()


def test_delete_thoroughly_deletes_all_revision_history():
    with (
        patch.object(Command, 'delete_all') as delete_all,
        patch.object(Command, 'repair_has_unpublished_changes'),
    ):
        Command().delete_thoroughly()

    delete_all.assert_has_calls([call(ReversionRevision), call(Revision)], any_order=False)
