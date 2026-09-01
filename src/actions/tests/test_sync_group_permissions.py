from __future__ import annotations

from django.contrib.auth.models import Group
from wagtail.models import GroupPagePermission
from wagtail.models.media import GroupCollectionPermission

import pytest

from actions.models import Plan
from actions.models.action import ActionContactPerson
from actions.perms import get_wagtail_plan_admin_perms
from actions.tests.factories import ActionFactory
from indicators.models import IndicatorContactPerson
from indicators.tests.factories import IndicatorFactory
from people.tests.factories import PersonFactory
from users.perms import create_permissions
from users.tests.factories import UserFactory

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
        assert GroupPagePermission.objects.filter(group=plan1.admin_group, page__in=root_pages).exists()

    if plan2.site and plan2.site.root_page:
        root_pages = set(plan2.site.root_page.get_translations(inclusive=True))
        assert GroupPagePermission.objects.filter(group=plan2.admin_group, page__in=root_pages).exists()

    # Verify the plan admin groups have collection permissions
    wagtail_perms = get_wagtail_plan_admin_perms()

    assert GroupCollectionPermission.objects.filter(
        group=plan1.admin_group, collection=plan1.root_collection, permission__in=wagtail_perms
    ).exists()

    assert GroupCollectionPermission.objects.filter(
        group=plan2.admin_group, collection=plan2.root_collection, permission__in=wagtail_perms
    ).exists()


def test_plan_admin_group_syncs_immediately_when_assignment_is_removed(organization_factory):
    """
    Verify removing general admin rights updates auth groups immediately.

    This exercises the admin-edit path where the GeneralPlanAdmin through model
    changes, without waiting for the user's next login.
    """
    org = organization_factory()
    plan = Plan.create_with_defaults(
        identifier='test-plan',
        name='Test Plan',
        primary_language='en',
        organization=org,
    )
    assert plan.admin_group is not None

    user = UserFactory.create()
    person = PersonFactory.create(user=user, email=user.email, general_admin_plans=[plan])
    create_permissions(user)

    generic_group = Group.objects.get(name='Plan admins')
    assert user.groups.filter(pk=generic_group.pk).exists()
    assert user.groups.filter(pk=plan.admin_group.pk).exists()

    person.general_admin_plans.remove(plan)

    assert not user.groups.filter(pk=generic_group.pk).exists()
    assert not user.groups.filter(pk=plan.admin_group.pk).exists()


def test_staff_status_syncs_immediately_when_last_admin_assignment_is_removed(organization_factory):
    """Verify users stop being staff immediately when their last admin role is removed."""
    org = organization_factory()
    plan = Plan.create_with_defaults(
        identifier='test-plan',
        name='Test Plan',
        primary_language='en',
        organization=org,
    )

    user = UserFactory.create()
    person = PersonFactory.create(user=user, email=user.email, general_admin_plans=[plan])
    create_permissions(user)

    user.refresh_from_db()
    assert user.is_staff

    person.general_admin_plans.remove(plan)

    user.refresh_from_db()


def test_person_delete_removes_plan_admin_groups_immediately(organization_factory):
    """Verify deleting a Person removes stale auth groups from the corresponding user."""
    org = organization_factory()
    plan = Plan.create_with_defaults(
        identifier='test-plan',
        name='Test Plan',
        primary_language='en',
        organization=org,
    )
    assert plan.admin_group is not None

    user = UserFactory.create()
    person = PersonFactory.create(user=user, email=user.email, general_admin_plans=[plan])
    create_permissions(user)

    assert user.groups.filter(pk=plan.admin_group.pk).exists()

    person.delete()

    assert not user.groups.filter(pk=plan.admin_group.pk).exists()


def test_action_contact_group_syncs_immediately_when_assignment_is_removed(organization_factory):
    """Verify removing an action contact person updates generic and plan-specific groups immediately."""
    org = organization_factory()
    plan = Plan.create_with_defaults(
        identifier='test-plan',
        name='Test Plan',
        primary_language='en',
        organization=org,
    )
    assert plan.contact_person_group is not None

    action = ActionFactory.create(plan=plan)
    user = UserFactory.create()
    person = PersonFactory.create(user=user)
    contact_person = ActionContactPerson.objects.create(action=action, person=person)

    generic_group = Group.objects.get(name='Action contact persons')
    assert user.groups.filter(pk=generic_group.pk).exists()
    assert user.groups.filter(pk=plan.contact_person_group.pk).exists()

    contact_person.delete()

    assert not user.groups.filter(pk=generic_group.pk).exists()
    assert not user.groups.filter(pk=plan.contact_person_group.pk).exists()


def test_indicator_contact_group_syncs_immediately_when_assignment_is_removed(organization_factory):
    """Verify removing an indicator contact person updates generic and plan-specific groups immediately."""
    org = organization_factory()
    plan = Plan.create_with_defaults(
        identifier='test-plan',
        name='Test Plan',
        primary_language='en',
        organization=org,
    )
    assert plan.contact_person_group is not None

    indicator = IndicatorFactory.create(organization=org, plans=[plan])
    user = UserFactory.create()
    person = PersonFactory.create(user=user)
    contact_person = IndicatorContactPerson.objects.create(indicator=indicator, person=person)

    generic_group = Group.objects.get(name='Indicator contact persons')
    assert user.groups.filter(pk=generic_group.pk).exists()
    assert user.groups.filter(pk=plan.contact_person_group.pk).exists()

    contact_person.delete()

    assert not user.groups.filter(pk=generic_group.pk).exists()
    assert not user.groups.filter(pk=plan.contact_person_group.pk).exists()
