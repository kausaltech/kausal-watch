from unittest.mock import call, patch

from reversion.models import Revision as ReversionRevision
from wagtail.models import Revision

import pytest

from actions.management.commands.destructively_trim_db import Command
from actions.models import Plan
from actions.models.public_user import PublicUser
from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.models import Client
from admin_site.tests.factories import ClientFactory, ClientPlanFactory
from orgs.models import Organization
from pages.tests.factories import CategoryTypePageFactory, StaticPageFactory

pytestmark = pytest.mark.django_db


def test_delete_missing_object_wagtail_revisions_keeps_existing_drafts():
    action = ActionFactory.create()
    revision = action.save_revision(user=None)

    command = Command()
    command.delete_entries_for_missing_objects(Revision)
    command.repair_has_unpublished_changes()

    action.refresh_from_db()
    assert action.latest_revision_id == revision.id
    assert Revision.objects.filter(id=revision.id).exists()


def test_delete_missing_object_wagtail_revisions_deletes_orphaned_drafts():
    action = ActionFactory.create()
    revision = action.save_revision(user=None)
    action.delete()

    command = Command()
    command.delete_entries_for_missing_objects(Revision)
    command.repair_has_unpublished_changes()

    assert not Revision.objects.filter(id=revision.id).exists()


def test_delete_missing_object_wagtail_revisions_handles_page_subclasses(plan_with_pages):
    page = StaticPageFactory.create(parent=plan_with_pages.root_page)
    revision = page.save_revision(user=None)

    command = Command()
    command.delete_entries_for_missing_objects(Revision)
    command.repair_has_unpublished_changes()

    page.refresh_from_db()
    assert page.latest_revision_id == revision.id
    assert Revision.objects.filter(id=revision.id).exists()


def test_delete_missing_object_wagtail_revisions_handles_multi_table_page_subclasses(plan_with_pages, category_type):
    page = CategoryTypePageFactory.create(parent=plan_with_pages.root_page, category_type=category_type)
    revision = page.save_revision(user=None)

    command = Command()
    command.delete_entries_for_missing_objects(Revision)
    command.repair_has_unpublished_changes()

    page.refresh_from_db()
    assert page.latest_revision_id == revision.id
    assert Revision.objects.filter(id=revision.id).exists()


def test_delete_thoroughly_deletes_all_revision_history():
    with (
        patch.object(Command, 'delete_all') as delete_all,
        patch.object(Command, 'repair_has_unpublished_changes'),
    ):
        Command().delete_thoroughly()

    delete_all.assert_has_calls([call(ReversionRevision), call(Revision)], any_order=False)


def test_delete_data_deletes_public_users_of_deleted_clients_only():
    kept_plan = PlanFactory.create()
    deleted_plan = PlanFactory.create()
    shared_client = ClientFactory.create()
    deleted_client = ClientFactory.create()
    ClientPlanFactory.create(client=shared_client, plan=kept_plan)
    ClientPlanFactory.create(client=shared_client, plan=deleted_plan)
    ClientPlanFactory.create(client=deleted_client, plan=deleted_plan)
    kept_user = PublicUser.objects.create(email='kept@example.com', client=shared_client)
    deleted_user = PublicUser.objects.create(email='deleted@example.com', client=deleted_client)

    Command().delete_data(Plan.objects.filter(id=deleted_plan.id), Organization.objects.none())

    assert PublicUser.objects.filter(id=kept_user.id).exists()
    assert not PublicUser.objects.filter(id=deleted_user.id).exists()
    assert Client.objects.filter(id=shared_client.id).exists()
    assert not Client.objects.filter(id=deleted_client.id).exists()
