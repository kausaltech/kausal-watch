from __future__ import annotations

from django.contrib.auth.models import Group
from wagtail.models import GroupPagePermission

import pytest

from actions.models import Plan
from actions.perms import get_wagtail_plan_admin_perms, sync_group_permissions

pytestmark = pytest.mark.django_db


def test_sync_group_permissions_creates_required_groups_for_plans(organization_factory):
    """Test that sync_group_permissions creates and syncs groups for multiple plans."""
    # Create two plans using create_with_defaults
    org = organization_factory()
    plan1 = Plan.create_with_defaults(
        identifier='test-plan-1',
        name='Test Plan 1',
        primary_language='en',
        organization=org,
    )
    plan2 = Plan.create_with_defaults(
        identifier='test-plan-2',
        name='Test Plan 2',
        primary_language='en',
        organization=org,
    )

    # Verify plans have root collections (created automatically by create_with_defaults)
    assert plan1.root_collection is not None
    assert plan2.root_collection is not None

    # Plans should have their groups created automatically
    assert plan1.admin_group is not None
    assert plan1.contact_person_group is not None
    assert plan2.admin_group is not None
    assert plan2.contact_person_group is not None

    # Store group IDs before sync
    plan1_admin_group_id = plan1.admin_group.pk
    plan1_contact_group_id = plan1.contact_person_group.pk
    plan2_admin_group_id = plan2.admin_group.pk
    plan2_contact_group_id = plan2.contact_person_group.pk

    # Run sync_group_permissions
    sync_group_permissions()

    # Verify the groups still exist
    assert Group.objects.filter(id=plan1_admin_group_id).exists()
    assert Group.objects.filter(id=plan1_contact_group_id).exists()
    assert Group.objects.filter(id=plan2_admin_group_id).exists()
    assert Group.objects.filter(id=plan2_contact_group_id).exists()

    # Verify the global groups exist
    assert Group.objects.filter(name='Action contact persons').exists()
    assert Group.objects.filter(name='Indicator contact persons').exists()
    assert Group.objects.filter(name='Plan admins').exists()

    # Verify the plan admin groups have page permissions if root pages exist
    plan1.refresh_from_db()
    plan2.refresh_from_db()

    if plan1.site and plan1.site.root_page:
        root_pages = set(plan1.site.root_page.get_translations(inclusive=True))
        assert GroupPagePermission.objects.filter(
            group=plan1.admin_group,
            page__in=root_pages
        ).exists()

    if plan2.site and plan2.site.root_page:
        root_pages = set(plan2.site.root_page.get_translations(inclusive=True))
        assert GroupPagePermission.objects.filter(
            group=plan2.admin_group,
            page__in=root_pages
        ).exists()

    # Verify the plan admin groups have collection permissions
    from wagtail.models.media import GroupCollectionPermission
    wagtail_perms = get_wagtail_plan_admin_perms()

    assert GroupCollectionPermission.objects.filter(
        group=plan1.admin_group,
        collection=plan1.root_collection,
        permission__in=wagtail_perms
    ).exists()

    assert GroupCollectionPermission.objects.filter(
        group=plan2.admin_group,
        collection=plan2.root_collection,
        permission__in=wagtail_perms
    ).exists()
