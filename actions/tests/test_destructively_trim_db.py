from unittest.mock import call, patch

from django.db.models.signals import post_delete, post_save
from reversion.models import Revision as ReversionRevision
from wagtail.models import Revision, Site

import factory
import pytest
from wagtail_localize.models import String, TranslatableObject, TranslationSource

from actions.management.commands.destructively_trim_db import Command
from actions.models import Plan
from actions.tests.factories import ActionFactory, PlanFactory
from indicators.models.common_indicator import CommonIndicator, FrameworkIndicator, PlanCommonIndicator
from indicators.models.metadata import Framework
from indicators.tests.factories import CommonIndicatorFactory, IndicatorFactory
from pages.models import PlanRootPage
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


def test_delete_orphaned_translation_data_keeps_live_objects(plan_with_pages):
    page = StaticPageFactory.create(parent=plan_with_pages.root_page)
    TranslationSource.update_or_create_from_instance(page)
    assert TranslatableObject.objects.filter(translation_key=page.translation_key).exists()

    Command().delete_orphaned_translation_data()

    assert TranslatableObject.objects.filter(translation_key=page.translation_key).exists()
    assert TranslationSource.objects.filter(object_id=page.translation_key).exists()


def test_delete_orphaned_translation_data_deletes_orphans(plan_with_pages):
    page = StaticPageFactory.create(parent=plan_with_pages.root_page)
    TranslationSource.update_or_create_from_instance(page)
    translation_key = page.translation_key
    string_count = String.objects.count()
    assert string_count > 0

    # Delete the page with signals muted, exactly as the trim command does. This suppresses
    # wagtail_localize's own post_delete cleanup, leaving the translation data orphaned.
    with factory.django.mute_signals(post_delete):
        page.delete()
    assert TranslatableObject.objects.filter(translation_key=translation_key).exists()

    Command().delete_orphaned_translation_data()

    assert not TranslatableObject.objects.filter(translation_key=translation_key).exists()
    assert not TranslationSource.objects.filter(object_id=translation_key).exists()
    # The deleted page's strings are gone (count dropped), and no orphaned strings are left behind;
    # strings still referenced by other, live pages are kept.
    assert String.objects.count() < string_count
    assert not String.objects.filter(segments__isnull=True).exists()


def test_delete_orphaned_plan_pages(plan_with_pages):
    from audit_logging.models import PlanScopedModelLogEntry, PlanScopedPageLogEntry

    kept_root_id = plan_with_pages.root_page.id

    orphan_plan = PlanFactory.create()
    with factory.django.mute_signals(post_save):
        orphan_plan.create_default_site()
        orphan_plan.save()
    orphan_root_id = orphan_plan.root_page.id
    orphan_site_id = orphan_plan.site_id
    assert orphan_site_id is not None

    # Simulate a plan whose page tree was left behind. Clear the PROTECT-ed log entries first (as
    # Plan.delete() itself does), then bulk-delete the Plan row so its override's page cleanup is
    # bypassed and the PlanRootPage subtree and Site survive, as translated locale trees do in
    # practice.
    PlanScopedPageLogEntry.objects.filter(plan=orphan_plan).delete()
    PlanScopedModelLogEntry.objects.filter(plan=orphan_plan).delete()
    Plan.objects.filter(pk=orphan_plan.pk).delete()
    assert PlanRootPage.objects.filter(id=orphan_root_id).exists()

    Command().delete_orphaned_plan_pages()

    assert not PlanRootPage.objects.filter(id=orphan_root_id).exists()
    assert not Site.objects.filter(id=orphan_site_id).exists()
    assert PlanRootPage.objects.filter(id=kept_root_id).exists()


def test_prune_unused_common_indicators():
    # Kept: referenced by a surviving indicator (Indicator.common is on_delete=PROTECT).
    indicator = IndicatorFactory.create()
    assert indicator.common is not None
    used_by_indicator = indicator.common
    # Kept: linked to a retained plan.
    plan = PlanFactory.create()
    used_by_plan = CommonIndicatorFactory.create()
    PlanCommonIndicator.objects.create(common_indicator=used_by_plan, plan=plan)
    # Deleted: not linked to any plan or indicator; leaves its framework empty.
    framework = Framework.objects.create(identifier='fw', name='Framework')
    unused = CommonIndicatorFactory.create()
    FrameworkIndicator.objects.create(common_indicator=unused, framework=framework, identifier='fi')

    Command().prune_unused_common_indicators()

    assert CommonIndicator.objects.filter(pk=used_by_indicator.pk).exists()
    assert CommonIndicator.objects.filter(pk=used_by_plan.pk).exists()
    assert not CommonIndicator.objects.filter(pk=unused.pk).exists()
    assert not Framework.objects.filter(pk=framework.pk).exists()


def test_delete_thoroughly_deletes_all_revision_history():
    with (
        patch.object(Command, 'delete_all') as delete_all,
        patch.object(Command, 'repair_has_unpublished_changes'),
    ):
        Command().delete_thoroughly()

    delete_all.assert_has_calls([call(ReversionRevision), call(Revision)], any_order=False)
