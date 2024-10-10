from __future__ import annotations

from typing import Any

import pytest

from actions.perms import _make_organization_tree, calculate_people_with_login_rights
from orgs.models import Organization
from orgs.tests.fixtures import *  # noqa: F403
from people.models import Person

pytestmark = pytest.mark.django_db


ORG_TREE = """
    1
    2
        2.1
        2.2
            2.2.1
    3
        3.1
"""


@pytest.fixture()
def organization_hierarchy(organization_hierarchy_factory):
    return organization_hierarchy_factory(ORG_TREE)


def get_org_pk(name: str) -> int:
    return Organization.objects.get(name=name).pk


@pytest.fixture()
def test_data(organization_hierarchy):
    all_orgs = _make_organization_tree(Organization.objects.order_by('path').all())
    return {
        'superusers': {1},
        'general_plan_admins': {2},
        'action_contact_persons': {3},
        'indicator_contact_persons': {4},
        'responsible_orgs': {get_org_pk("3.1")},
        'primary_orgs': {get_org_pk("1")},
        'indicator_orgs': {get_org_pk("2.2.1")},
        'organization_plan_admins': {
            # (org, person)
            (get_org_pk("2.1"), 3),
            (get_org_pk("2.2.1"), 4),
            (get_org_pk("3"), 5),
        },
        'all_orgs': all_orgs,
    }


@pytest.fixture()
def create_models(  # noqa: C901
        superuser,
        plan,
        user_factory,
        person_factory,
        action_contact_factory,
        indicator_contact_factory,
        action_responsible_party_factory,
        action_factory,
        indicator_factory,
        organization_plan_admin_factory,
):
    """Return the same test data but ensure there are models matching it."""
    def _create_models(test_data) -> dict[str, Any]:
        for pk in test_data['superusers']:
            person_factory(user=superuser, pk=pk)
        for pk in test_data['general_plan_admins']:
            person_factory(general_admin_plans=[plan], pk=pk)
        for pk in test_data['action_contact_persons']:
            person = person_factory(pk=pk)
            action_contact_factory(person=person)
        for pk in test_data['indicator_contact_persons']:
            person = person_factory(pk=pk)
            ic = indicator_contact_factory(person=person)
            ic.indicator.plans.set([plan])
        for pk in test_data['responsible_orgs']:
            action_responsible_party_factory(organization_id=pk)
        for pk in test_data['primary_orgs']:
            action_factory(primary_org_id=pk, plan=plan)
        for pk in test_data['indicator_orgs']:
            indicator = indicator_factory(organization_id=pk)
            indicator.plans.set([plan])
        for org_pk, person_pk in test_data['organization_plan_admins']:
            if not Person.objects.filter(pk=person_pk).exists():
                person_factory(pk=person_pk)
            organization_plan_admin_factory(
                plan=plan,
                organization_id=org_pk,
                person_id=person_pk,
            )
        return test_data
    return _create_models


def test_superusers(test_data):
    result = calculate_people_with_login_rights(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=set(),
        indicator_contact_persons=set(),
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    )
    assert result == {1}


def test_general_plan_admins(test_data):
    result = calculate_people_with_login_rights(
        superusers=test_data['superusers'],
        general_plan_admins=test_data['general_plan_admins'],
        action_contact_persons=set(),
        indicator_contact_persons=set(),
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    )
    assert result == {1, 2}


def test_action_contact_persons(test_data):
    result = calculate_people_with_login_rights(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=test_data['action_contact_persons'],
        indicator_contact_persons=set(),
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    )
    assert result == {1, 3}


def test_indicator_contact_persons(test_data):
    result = calculate_people_with_login_rights(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=set(),
        indicator_contact_persons=test_data['indicator_contact_persons'],
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    )
    assert result == {1, 4}


def test_organization_plan_admins(test_data):
    result = calculate_people_with_login_rights(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=set(),
        indicator_contact_persons=set(),
        responsible_orgs=test_data['responsible_orgs'],
        primary_orgs=test_data['primary_orgs'],
        indicator_orgs=test_data['indicator_orgs'],
        organization_plan_admins=test_data['organization_plan_admins'],
        all_orgs=test_data['all_orgs'],
    )
    assert result == {1, 4, 5}


def assert_user_access_matches_result(result: set[int]):
    for pk in result:
        person = Person.objects.get(pk=pk)
        assert person.user
        assert person.user.can_access_admin()
    for person in Person.objects.all():
        if person.pk in result:
            continue
        user = person.user
        assert user
        assert not user.can_access_admin()


def test_superusers_match_user_can_access_admin(test_data, create_models):
    test_data_with_models = create_models(dict(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=set(),
        indicator_contact_persons=set(),
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    ))
    result = calculate_people_with_login_rights(**test_data_with_models)
    assert_user_access_matches_result(result)


def test_general_plan_admins_match_user_can_access_admin(test_data, create_models):
    test_data_with_models = create_models(dict(
        superusers=test_data['superusers'],
        general_plan_admins=test_data['general_plan_admins'],
        action_contact_persons=set(),
        indicator_contact_persons=set(),
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    ))
    result = calculate_people_with_login_rights(**test_data_with_models)
    assert_user_access_matches_result(result)


def test_action_contact_persons_match_user_can_access_admin(test_data, create_models):
    test_data_with_models = create_models(dict(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=test_data['action_contact_persons'],
        indicator_contact_persons=set(),
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    ))
    result = calculate_people_with_login_rights(**test_data_with_models)
    assert_user_access_matches_result(result)


def test_indicator_contact_persons_match_user_can_access_admin(test_data, create_models):
    test_data_with_models = create_models(dict(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=set(),
        indicator_contact_persons=test_data['indicator_contact_persons'],
        responsible_orgs=set(),
        primary_orgs=set(),
        indicator_orgs=set(),
        organization_plan_admins=set(),
        all_orgs=test_data['all_orgs'],
    ))
    result = calculate_people_with_login_rights(**test_data_with_models)
    assert_user_access_matches_result(result)


def test_organization_plan_admins_match_user_can_access_admin(test_data, create_models):
    test_data_with_models = create_models(dict(
        superusers=test_data['superusers'],
        general_plan_admins=set(),
        action_contact_persons=set(),
        indicator_contact_persons=set(),
        responsible_orgs=test_data['responsible_orgs'],
        primary_orgs=test_data['primary_orgs'],
        indicator_orgs=test_data['indicator_orgs'],
        organization_plan_admins=test_data['organization_plan_admins'],
        all_orgs=test_data['all_orgs'],
    ))
    result = calculate_people_with_login_rights(**test_data_with_models)
    assert_user_access_matches_result(result)
