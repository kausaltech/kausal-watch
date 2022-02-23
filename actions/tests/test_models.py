import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from actions.models import Action
from actions.tests.factories import ActionFactory, CategoryFactory
from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


def test_plan_can_be_saved(plan):
    pass


def test_plan_get_related_organizations(plan):
    assert plan.organization
    org = OrganizationFactory()
    sub_org1 = OrganizationFactory(parent=plan.organization)
    sub_org2 = OrganizationFactory(parent=org)
    result = list(plan.get_related_organizations())
    assert result == [plan.organization, sub_org1]
    plan.related_organizations.add(org)
    result = list(plan.get_related_organizations())
    assert result == [plan.organization, sub_org1, org, sub_org2]


def test_action_query_set_modifiable_by_not_modifiable(action, user):
    assert action not in Action.objects.modifiable_by(user)


def test_action_query_set_modifiable_by_superuser(action, superuser):
    assert action in Action.objects.modifiable_by(superuser)


def test_action_query_set_modifiable_by_plan_admin(action, plan_admin_user):
    assert action in Action.objects.modifiable_by(plan_admin_user)


def test_action_query_set_modifiable_by_contact_person(action, action_contact):
    assert action in Action.objects.modifiable_by(action_contact.person.user)


def test_action_query_set_modifiable_by_distinct(action, user, person, action_contact):
    assert person.user == user
    assert person == action_contact.person
    assert list(Action.objects.modifiable_by(user)) == [action]
    # Make user a plan admin as well
    person.general_admin_plans.add(action.plan)
    assert list(Action.objects.modifiable_by(user)) == [action]
    # When we remove the user from the action contacts, it should still be able to modify
    action_contact.delete()
    assert list(Action.objects.modifiable_by(user)) == [action]


def test_action_can_be_saved():
    ActionFactory()


def test_action_no_duplicate_identifier_per_plan(plan):
    Action.objects.create(plan=plan, name='Test action 1', identifier='id')
    with pytest.raises(IntegrityError):
        Action.objects.create(plan=plan, name='Test action 2', identifier='id')


@pytest.mark.parametrize('color', ['invalid', '#fffffg', '#00'])
def test_category_color_invalid(color):
    category = CategoryFactory()
    category.color = color
    with pytest.raises(ValidationError):
        category.full_clean()


@pytest.mark.parametrize('color', ['#ffFFff', '#000', 'red', 'rgb(1,2,3)', 'rgba(0%, 100%, 100%, 0.5)'])
def test_category_color_valid(color):
    category = CategoryFactory()
    category.color = color
    category.full_clean()
