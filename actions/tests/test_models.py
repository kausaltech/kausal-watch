import pytest
from datetime import date, datetime, timedelta
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from wagtail.models import Locale

from actions.models import Action
from actions.tests.factories import ActionFactory, CategoryFactory, CategoryTypeFactory
from pages.models import CategoryPage, CategoryTypePage

pytestmark = pytest.mark.django_db


def test_plan_can_be_saved(plan):
    pass


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
    locale = Locale.objects.get(language_code__iexact=language)
    translated_root_page = plan.root_page.get_translation(locale)
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


def test_category_move_to_new_parent_changes_page_hierarchy(plan_with_pages):
    category_type = CategoryTypeFactory(synchronize_with_pages=True, plan=plan_with_pages)
    locale = Locale.objects.get(language_code=plan_with_pages.primary_language)
    ct_page = category_type.category_type_pages.filter(locale=locale).get()
    cat1 = CategoryFactory(type=category_type)
    cat2 = CategoryFactory(type=category_type)
    assert cat1.category_pages.filter(locale=locale).get().get_parent().specific == ct_page
    assert cat2.category_pages.filter(locale=locale).get().get_parent().specific == ct_page
    cat2.parent = cat1
    cat2.save()
    assert cat1.category_pages.filter(locale=locale).get().get_parent().specific == ct_page
    assert (cat2.category_pages.filter(locale=locale).get().get_parent().specific ==
            cat1.category_pages.filter(locale=locale).get())


def test_category_move_to_new_sibling_changes_page_hierarchy(plan_with_pages):
    category_type = CategoryTypeFactory(synchronize_with_pages=True, plan=plan_with_pages)
    locale = Locale.objects.get(language_code=plan_with_pages.primary_language)
    cat1 = CategoryFactory(type=category_type)
    cat2 = CategoryFactory(type=category_type)
    assert cat1.order < cat2.order
    assert (cat1.category_pages.filter(locale=locale).get().get_next_sibling().specific ==
            cat2.category_pages.filter(locale=locale).get())
    cat1.order = cat2.order + 1
    cat1.save()
    assert (cat2.category_pages.filter(locale=locale).get().get_next_sibling().specific ==
            cat1.category_pages.filter(locale=locale).get())


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


def test_plan_should_trigger_daily_notifications_disabled(plan):
    assert not plan.notification_settings.notifications_enabled
    send_at_time = plan.notification_settings.send_at_time
    now = datetime.combine(date(2000, 1, 1), send_at_time, plan.tzinfo)
    assert not plan.should_trigger_daily_notifications(now)


@pytest.mark.parametrize('notification_settings__notifications_enabled', [True])
def test_plan_should_trigger_daily_notifications_never_triggered(plan):
    assert plan.notification_settings.notifications_enabled
    assert not plan.daily_notifications_triggered_at
    send_at_time = plan.notification_settings.send_at_time
    now = datetime.combine(date(2000, 1, 1), send_at_time, plan.tzinfo)
    assert plan.should_trigger_daily_notifications(now)


@pytest.mark.parametrize('notification_settings__notifications_enabled', [True])
def test_plan_should_trigger_daily_notifications_not_due_yet(plan):
    assert plan.notification_settings.notifications_enabled
    send_at_time = plan.notification_settings.send_at_time
    plan.daily_notifications_triggered_at = datetime.combine(date(2000, 1, 1), send_at_time, plan.tzinfo)
    now = plan.daily_notifications_triggered_at + timedelta(hours=23, minutes=59)
    assert not plan.should_trigger_daily_notifications(now)


@pytest.mark.parametrize('notification_settings__notifications_enabled', [True])
def test_plan_should_trigger_daily_notifications_due(plan):
    assert plan.notification_settings.notifications_enabled
    send_at_time = plan.notification_settings.send_at_time
    plan.daily_notifications_triggered_at = datetime.combine(date(2000, 1, 1), send_at_time, plan.tzinfo)
    now = plan.daily_notifications_triggered_at + timedelta(days=1)
    assert plan.should_trigger_daily_notifications(now)
