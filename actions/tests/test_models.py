import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from wagtail.core.models import Locale

from actions.models import Action
from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory
from orgs.tests.factories import OrganizationFactory
from pages.models import CategoryPage, CategoryTypePage

pytestmark = pytest.mark.django_db


def test_plan_can_be_saved(plan):
    pass


def test_plan_get_related_organizations(plan):
    assert plan.organization
    plan_org = plan.organization
    org = OrganizationFactory()
    # Creating a new root org might've changed the path of plan_org
    plan_org.refresh_from_db()
    sub_org1 = OrganizationFactory(parent=plan.organization)
    sub_org2 = OrganizationFactory(parent=org)
    result = list(plan.get_related_organizations())
    assert result == [plan.organization, sub_org1]
    plan.related_organizations.add(org)
    result = set(plan.get_related_organizations())
    assert result == set([plan_org, sub_org1, org, sub_org2])


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


def test_category_type_synchronize_pages_when_synchronization_activated(plan_with_pages, category):
    plan = plan_with_pages
    assert not plan.root_page.get_children().type(CategoryTypePage).exists()
    assert not plan.root_page.get_children().type(CategoryPage).exists()
    category.type.synchronize_with_pages = True
    category.type.save()
    ct_page = category.type.category_type_pages.child_of(plan.root_page).get()
    page = ct_page.get_children().get()
    assert page.title == category.name


def test_category_type_synchronize_pages_translated(plan_with_pages):
    category = CategoryFactory(type__synchronize_with_pages=True, type__plan=plan_with_pages)
    plan = plan_with_pages
    language = plan.other_languages[0]
    locale = Locale.objects.create(language_code=language)
    translated_root_page = plan.root_page.copy_for_translation(locale)
    category.type.synchronize_pages()
    ct_page = category.type.category_type_pages.child_of(translated_root_page).get()
    assert ct_page.title == category.type.name
    page = ct_page.get_children().get()
    assert page.title == getattr(category, f'name_{language}')


def test_category_type_synchronize_pages_exists(plan_with_pages):
    category = CategoryFactory(type__synchronize_with_pages=True, type__plan=plan_with_pages)
    plan = plan_with_pages
    category.type.synchronize_pages()
    ct_page = category.type.category_type_pages.child_of(plan.root_page).get()
    old_page_title = ct_page.title
    category.type.name = "Changed category type name"
    category.type.save()
    category.name = "Changed category name"
    category.save()
    category.type.synchronize_pages()
    # assert ct_page.title == category.type.name
    assert ct_page.title == old_page_title
    page = ct_page.get_children().get()
    assert page.title == category.name


def test_category_type_creating_category_creates_page(plan_with_pages):
    category_type = CategoryTypeFactory(synchronize_with_pages=True, plan=plan_with_pages)
    category_type.synchronize_pages()
    ct_page = category_type.category_type_pages.child_of(category_type.plan.root_page).get()
    assert not ct_page.get_children().exists()
    CategoryFactory(type=category_type)
    ct_page.refresh_from_db()
    assert ct_page.get_children().exists()


def test_plan_action_staleness_returns_default(plan):
    assert plan.get_action_days_until_considered_stale() == plan.DEFAULT_ACTION_DAYS_UNTIL_CONSIDERED_STALE


def test_plan_action_staleness_returns_set_value(plan_factory):
    plan1 = plan_factory()
    plan2 = plan_factory()
    plan3 = plan_factory()
    plan1.action_days_until_considered_stale = 230
    plan1.save()
    plan2.action_days_until_considered_stale = 231
    plan2.save()
    plan3.action_days_until_considered_stale = 0
    plan3.save()
    assert plan1.get_action_days_until_considered_stale() == 230
    assert plan2.get_action_days_until_considered_stale() == 231
    assert plan3.get_action_days_until_considered_stale() == 0
