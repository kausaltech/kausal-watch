from datetime import date

from django.core.exceptions import ValidationError

import pytest

from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory
from indicators.models import Indicator
from indicators.tests.factories import (
    IndicatorContactFactory,
    IndicatorFactory,
    IndicatorLevelFactory,
    IndicatorValueFactory,
)
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory

pytestmark = pytest.mark.django_db


def test_indicator_updated_values_due_at_too_early():
    indicator = IndicatorFactory.create()
    assert indicator.updated_values_due_at is None
    value = IndicatorValueFactory(indicator=indicator, date=date(2020, 12, 31))
    indicator.handle_values_update()
    assert indicator.latest_value == value
    # Try to set a due date so that there is already a value within the previous year
    indicator.updated_values_due_at = date(2021, 3, 1)
    with pytest.raises(ValidationError):
        indicator.full_clean()


@pytest.mark.parametrize(
    ('time_resolution', 'should_raise'),
    [
        ('year', False),
        ('month', True),
        ('week', True),
        ('day', True),
    ],
)
def test_indicator_updated_values_due_at_resolution(time_resolution, should_raise):
    indicator = IndicatorFactory.create(time_resolution=time_resolution, updated_values_due_at=date(2020, 1, 1))
    if should_raise:
        with pytest.raises(ValidationError):
            indicator.full_clean()
    else:
        indicator.full_clean()


def test_indicator_plans_with_access_include_plans_with_same_organization(plan):
    indicator = IndicatorFactory.create(organization=plan.organization)
    assert plan in indicator.get_plans_with_access()
    assert plan not in indicator.plans.all()


def test_indicator_plans_with_access_dont_include_other_plans(plan):
    indicator = IndicatorFactory.create()
    assert plan not in indicator.get_plans_with_access()
    assert plan not in indicator.plans.all()


def test_indicator_plans_with_access_includes_indicator_plan(plan, indicator):
    indicator.plans.add(plan)
    assert plan in indicator.get_plans_with_access()


def test_indicator_handle_values_update_bumps_deadline_multiple_times():
    """
    Test that handle_values_update() bumps updated_values_due_at multiple times if needed.

    This covers the edge case where an indicator has an old deadline that's far behind the
    latest value date. A single 1-year bump isn't sufficient to pass the validation in clean().

    Fixes WATCH-BACKEND-3E4.
    """
    # Create indicator with a deadline that's way in the past
    indicator = IndicatorFactory.create(updated_values_due_at=date(2023, 6, 1))

    # Add a value for a much later date
    value = IndicatorValueFactory(indicator=indicator, date=date(2025, 12, 31))

    # Before handle_values_update, the deadline is way too early
    # (2023-06-01 is more than 1 year before 2025-12-31)
    assert indicator.updated_values_due_at == date(2023, 6, 1)

    # Call handle_values_update - this should bump the deadline enough times
    # so that it's more than 1 year after the latest value
    indicator.handle_values_update()

    # Verify latest_value was updated
    assert indicator.latest_value == value

    # The deadline should have been bumped to be > latest_value.date + 1 year
    # 2025-12-31 + 1 year = 2026-12-31, so deadline should be > 2026-12-31
    # Starting from 2023-06-01:
    # +1 year = 2024-06-01 (still <= 2026-12-31)
    # +1 year = 2025-06-01 (still <= 2026-12-31)
    # +1 year = 2026-06-01 (still <= 2026-12-31)
    # +1 year = 2027-06-01 (> 2026-12-31) ✓
    assert indicator.updated_values_due_at == date(2027, 6, 1)

    # Verify that full_clean passes (no ValidationError)
    indicator.full_clean()


def test_adminable_in_plan_by_general_admin_includes_descendant_organizations(plan, plan_admin_user):
    sub_org = OrganizationFactory.create(parent=plan.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    assert indicator in Indicator.objects.qs.adminable_in_plan_by(plan_admin_user, plan)


def test_adminable_in_plan_by_general_admin_includes_related_organization_descendants(plan, plan_admin_user):
    related_org = OrganizationFactory.create()
    plan.related_organizations.add(related_org)
    sub_org = OrganizationFactory.create(parent=related_org)
    indicator = IndicatorFactory.create(organization=sub_org)
    assert indicator in Indicator.objects.qs.adminable_in_plan_by(plan_admin_user, plan)


def test_adminable_in_plan_by_general_admin_includes_indicators_not_connected_to_the_plan(plan, plan_admin_user):
    indicator = IndicatorFactory.create(organization=plan.organization)
    assert plan not in indicator.plans.all()
    assert indicator in Indicator.objects.qs.adminable_in_plan_by(plan_admin_user, plan)


def test_adminable_in_plan_by_general_admin_lists_shared_indicators_once(plan, plan_admin_user):
    indicator = IndicatorFactory.create(organization=plan.organization)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    IndicatorLevelFactory.create(indicator=indicator)
    assert list(Indicator.objects.qs.adminable_in_plan_by(plan_admin_user, plan)) == [indicator]


def test_adminable_in_plan_by_general_admin_excludes_unrelated_organizations(plan, plan_admin_user):
    indicator = IndicatorFactory.create()
    assert indicator not in Indicator.objects.qs.adminable_in_plan_by(plan_admin_user, plan)


def test_adminable_in_plan_by_general_admin_excludes_indicators_of_other_plans(plan, plan_admin_user):
    sub_org = OrganizationFactory.create(parent=plan.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    IndicatorLevelFactory.create(indicator=indicator)
    assert indicator not in Indicator.objects.qs.adminable_in_plan_by(plan_admin_user, plan)


def test_adminable_in_plan_by_superuser_includes_indicators_of_other_plans(plan, superuser):
    sub_org = OrganizationFactory.create(parent=plan.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    IndicatorLevelFactory.create(indicator=indicator)
    assert indicator in Indicator.objects.qs.adminable_in_plan_by(superuser, plan)


def test_adminable_in_plan_by_includes_indicators_of_the_plan(plan, user):
    indicator = IndicatorFactory.create()
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    assert indicator in Indicator.objects.qs.adminable_in_plan_by(user, plan)


def test_adminable_in_plan_by_excludes_indicators_not_connected_to_the_plan(plan, user):
    indicator = IndicatorFactory.create(organization=plan.organization)
    assert indicator not in Indicator.objects.qs.adminable_in_plan_by(user, plan)


def test_adminable_in_plan_by_contact_person(plan, person):
    contact = IndicatorContactFactory.create(person=person)
    IndicatorLevelFactory.create(indicator=contact.indicator, plan=plan)
    assert person.user is not None
    assert contact.indicator in Indicator.objects.qs.adminable_in_plan_by(person.user, plan)


def test_adminable_in_plan_by_contact_person_excludes_other_plans(plan, person):
    contact = IndicatorContactFactory.create(person=person)
    IndicatorLevelFactory.create(indicator=contact.indicator)
    assert person.user is not None
    assert contact.indicator not in Indicator.objects.qs.adminable_in_plan_by(person.user, plan)


def test_indicator_modifiable_by_organization_plan_admin_of_ancestor_organization(plan):
    org_admin = OrganizationPlanAdminFactory.create(plan=plan)
    sub_org = OrganizationFactory.create(parent=org_admin.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    user = org_admin.person.user
    assert user is not None
    assert indicator in Indicator.objects.qs.modifiable_by(user)
    assert user.is_organization_admin_for_indicator(indicator)


def test_indicator_not_modifiable_by_organization_plan_admin_of_another_plan(plan):
    org_admin = OrganizationPlanAdminFactory.create(plan=plan)
    sub_org = OrganizationFactory.create(parent=org_admin.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    IndicatorLevelFactory.create(indicator=indicator)
    user = org_admin.person.user
    assert user is not None
    assert indicator not in Indicator.objects.qs.modifiable_by(user)
    assert not user.is_organization_admin_for_indicator(indicator)
    assert not user.can_modify_indicator(indicator)


def test_indicator_modifiable_by_general_admin_when_not_connected_to_any_plan(plan, plan_admin_user):
    sub_org = OrganizationFactory.create(parent=plan.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    assert indicator in Indicator.objects.qs.modifiable_by(plan_admin_user)
    assert plan_admin_user.can_modify_indicator(indicator)


def test_indicator_modifiable_by_general_admin_when_owned_by_the_plan_organization(plan, plan_admin_user):
    indicator = IndicatorFactory.create(organization=plan.organization)
    IndicatorLevelFactory.create(indicator=indicator)
    assert indicator in Indicator.objects.qs.modifiable_by(plan_admin_user)
    assert plan_admin_user.can_modify_indicator(indicator)


def test_indicator_not_modifiable_by_general_admin_of_another_plan(plan_admin_user):
    indicator = IndicatorFactory.create()
    IndicatorLevelFactory.create(indicator=indicator)
    assert indicator not in Indicator.objects.qs.modifiable_by(plan_admin_user)
    assert not plan_admin_user.can_modify_indicator(indicator)


def test_indicator_not_modifiable_in_another_plan_by_organization_plan_admin(plan):
    org_admin = OrganizationPlanAdminFactory.create(plan=plan)
    sub_org = OrganizationFactory.create(parent=org_admin.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    other_level = IndicatorLevelFactory.create(indicator=indicator)
    user = org_admin.person.user
    assert user is not None
    assert user.can_modify_indicator(indicator, plan=plan)
    assert not user.can_modify_indicator(indicator, plan=other_level.plan)


def test_indicator_not_modifiable_in_another_plan_by_general_admin(plan, plan_admin_user):
    indicator = IndicatorFactory.create(organization=plan.organization)
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    other_level = IndicatorLevelFactory.create(indicator=indicator)
    assert plan_admin_user.can_modify_indicator(indicator, plan=plan)
    assert not plan_admin_user.can_modify_indicator(indicator, plan=other_level.plan)


def test_indicator_not_modifiable_in_a_plan_without_access(plan, plan_admin_user):
    indicator = IndicatorFactory.create()
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    assert plan_admin_user.can_modify_indicator(indicator, plan=plan)
    unrelated_plan = PlanFactory.create()
    assert not plan_admin_user.can_modify_indicator(indicator, plan=unrelated_plan)


def test_indicator_plans_with_access_include_plans_related_to_the_organization(plan):
    sub_org = OrganizationFactory.create(parent=plan.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    assert plan in indicator.get_plans_with_access()


def test_indicator_plans_with_access_dont_include_related_plans_of_connected_indicators(plan):
    sub_org = OrganizationFactory.create(parent=plan.organization)
    indicator = IndicatorFactory.create(organization=sub_org)
    IndicatorLevelFactory.create(indicator=indicator)
    assert plan not in indicator.get_plans_with_access()


def _shared_indicator_with_other_adminable_plan(plan, plan_admin_person):
    """Set up an indicator of `plan` that another plan, in which the person is no admin, also uses."""
    other_plan = PlanFactory.create()
    # The person can access the other plan's admin, but only as a contact person for one of its actions
    ActionContactFactory.create(action=ActionFactory.create(plan=other_plan), person=plan_admin_person)
    indicator = IndicatorFactory.create()
    IndicatorLevelFactory.create(indicator=indicator, plan=plan)
    IndicatorLevelFactory.create(indicator=indicator, plan=other_plan)
    return indicator, other_plan


def test_indicator_permission_helper_allows_editing_in_the_administered_plan(plan, plan_admin_person):
    from indicators.wagtail_admin import IndicatorPermissionHelper

    indicator, _other_plan = _shared_indicator_with_other_adminable_plan(plan, plan_admin_person)
    user = plan_admin_person.user
    assert user is not None
    user.selected_admin_plan = plan
    user.save()

    assert user.get_active_admin_plan() == plan
    assert IndicatorPermissionHelper(model=Indicator).user_can_edit_obj(user, indicator)


def test_indicator_permission_helper_scopes_editing_to_the_active_plan(plan, plan_admin_person):
    from indicators.wagtail_admin import IndicatorPermissionHelper

    indicator, other_plan = _shared_indicator_with_other_adminable_plan(plan, plan_admin_person)
    user = plan_admin_person.user
    assert user is not None
    user.selected_admin_plan = other_plan
    user.save()

    # Editing would write the indicator level of the other plan, where the user is no admin
    assert user.get_active_admin_plan() == other_plan
    assert not IndicatorPermissionHelper(model=Indicator).user_can_edit_obj(user, indicator)


@pytest.fixture
def post_request_with_initial_plan(rf):
    """Put a POST request that was opened with `initial_plan` into the request context."""
    from contextlib import contextmanager

    from aplans.context_vars import ctx_request

    @contextmanager
    def func(initial_plan):
        request = rf.post('/admin/indicators/indicator/edit/1/')
        request.session = {'initial_plan_id': str(initial_plan.id)}
        with ctx_request.activate(request):
            yield request

    return func


def test_indicator_permission_helper_allows_editing_the_plan_the_form_was_opened_with(
    plan, plan_admin_person, post_request_with_initial_plan
):
    from indicators.wagtail_admin import IndicatorPermissionHelper

    indicator, other_plan = _shared_indicator_with_other_adminable_plan(plan, plan_admin_person)
    user = plan_admin_person.user
    assert user is not None
    # The user switched to the other plan after opening the form, so the level of `plan` is written
    user.selected_admin_plan = other_plan
    user.save()

    with post_request_with_initial_plan(plan):
        assert IndicatorPermissionHelper(model=Indicator).user_can_edit_obj(user, indicator)


def test_indicator_permission_helper_denies_editing_the_plan_the_form_was_opened_with(
    plan, plan_admin_person, post_request_with_initial_plan
):
    from indicators.wagtail_admin import IndicatorPermissionHelper

    indicator, other_plan = _shared_indicator_with_other_adminable_plan(plan, plan_admin_person)
    user = plan_admin_person.user
    assert user is not None
    user.selected_admin_plan = plan
    user.save()

    # The form was opened with the other plan, so its level is written even though `plan` is active
    with post_request_with_initial_plan(other_plan):
        assert not IndicatorPermissionHelper(model=Indicator).user_can_edit_obj(user, indicator)
