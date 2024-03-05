import pytest
from datetime import date, datetime, timedelta
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError
from django.utils import translation
from wagtail.models import Locale

from actions.models import Action, ActionContactPerson
from actions.tests.factories import (
    ActionFactory, ActionContactFactory, AttributeTextFactory, AttributeTypeFactory, CategoryFactory, CategoryTypeFactory, PlanFactory
)
from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin
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


@pytest.fixture
def category_type_with_category_hierarchy(category_type, category_level_factory, category_factory):
    """
    Constructs a three level category hierarchy with a balanced structure,
    with the category identifiers matching the hierarchy structure
    """
    ct_id = category_type
    for _ in range(0, 3):
        category_level_factory(type=category_type)

    p1 = category_factory(type=ct_id, identifier="C1", parent_id=None)

    p1_1 = category_factory(type=ct_id, identifier="C1.1", parent=p1)
    category_factory(type=ct_id, identifier="C1.1.1", parent=p1_1)
    category_factory(type=ct_id, identifier="C1.1.2", parent=p1_1)
    category_factory(type=ct_id, identifier="C1.1.3", parent=p1_1)

    p1_2 = category_factory(type=ct_id, identifier="C1.2", parent=p1)
    category_factory(type=ct_id, identifier="C1.2.1", parent=p1_2)
    category_factory(type=ct_id, identifier="C1.2.2", parent=p1_2)
    category_factory(type=ct_id, identifier="C1.2.3", parent=p1_2)

    p1_3 = category_factory(type=ct_id, identifier="C1.3", parent=p1)
    category_factory(type=ct_id, identifier="C1.3.1", parent=p1_3)
    category_factory(type=ct_id, identifier="C1.3.2", parent=p1_3)
    category_factory(type=ct_id, identifier="C1.3.3", parent=p1_3)

    p2 = category_factory(type=ct_id, identifier="C2", parent_id=None)

    p2_1 = category_factory(type=ct_id, identifier="C2.1", parent=p2)
    category_factory(type=ct_id, identifier="C2.1.1", parent=p2_1)
    category_factory(type=ct_id, identifier="C2.1.2", parent=p2_1)
    category_factory(type=ct_id, identifier="C2.1.3", parent=p2_1)

    p2_2 = category_factory(type=ct_id, identifier="C2.2", parent=p2)
    category_factory(type=ct_id, identifier="C2.2.1", parent=p2_2)
    category_factory(type=ct_id, identifier="C2.2.2", parent=p2_2)
    category_factory(type=ct_id, identifier="C2.2.3", parent=p2_2)

    p2_3 = category_factory(type=ct_id, identifier="C2.3", parent=p2)
    category_factory(type=ct_id, identifier="C2.3.1", parent=p2_3)
    category_factory(type=ct_id, identifier="C2.3.2", parent=p2_3)
    category_factory(type=ct_id, identifier="C2.3.3", parent=p2_3)

    return category_type


def test_categories_projected_by_level(category_type_with_category_hierarchy):
    ct = category_type_with_category_hierarchy
    cat_by_pk = {c.pk: c for c in ct.categories.all()}
    level_projections = ct.categories_projected_by_level()
    levels = ct.levels.all()

    for depth in range(0, 3):
        level_proj = level_projections[levels[depth].pk]
        for cat in cat_by_pk.values():
            identifier_prefix = cat.identifier[0:(2*(depth+1))]
            try:
                map_target = level_proj[cat.pk]
                assert map_target.identifier == identifier_prefix
            except KeyError:
                cat_depth = 0
                c = cat
                while c.parent is not None:
                    c = c.parent
                    cat_depth += 1
                # No levels deeper than the level of category x
                # contain a mapping for category x --
                # for these the key error is as expected
                assert cat_depth < depth


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


@pytest.mark.parametrize('editable_by', [
    InstancesEditableByMixin.EditableBy.CONTACT_PERSONS,
    InstancesEditableByMixin.EditableBy.MODERATORS,
])
def test_category_type_does_not_accept_action_specific_editability(editable_by):
    with pytest.raises(ValidationError):
        CategoryTypeFactory(instances_editable_by=editable_by).full_clean()


@pytest.mark.parametrize('editable_by', [
    InstancesEditableByMixin.EditableBy.AUTHENTICATED,
    InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
    InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
])
def test_category_type_accepts_non_action_specific_editability(editable_by):
    CategoryTypeFactory(instances_editable_by=editable_by).full_clean()


@pytest.mark.parametrize('model,scope_factory,editable_by_accepted,editable_by_raises', [
    ('action', PlanFactory, [
        # accepted
        InstancesEditableByMixin.EditableBy.AUTHENTICATED,
        InstancesEditableByMixin.EditableBy.CONTACT_PERSONS,
        InstancesEditableByMixin.EditableBy.MODERATORS,
        InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
        InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    ], [
        # raises
        # [never]
    ]),
    ('category', CategoryTypeFactory, [
        # accepted
        InstancesEditableByMixin.EditableBy.AUTHENTICATED,
        InstancesEditableByMixin.EditableBy.PLAN_ADMINS,
        InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    ], [
        # raises
        InstancesEditableByMixin.EditableBy.CONTACT_PERSONS,
        InstancesEditableByMixin.EditableBy.MODERATORS,
    ]),
])
def test_attribute_type_editability_validation(model, scope_factory, editable_by_accepted, editable_by_raises):
    scope = scope_factory()
    for editable_by in editable_by_accepted:
        AttributeTypeFactory(
           object_content_type=ContentType.objects.get(app_label='actions', model=model),
           scope=scope,
           instances_editable_by=editable_by,
        ).full_clean()
    for editable_by in editable_by_raises:
        with pytest.raises(ValidationError):
            AttributeTypeFactory(
               object_content_type=ContentType.objects.get(app_label='actions', model=model),
               scope=scope,
               instances_editable_by=editable_by,
            ).full_clean()


@pytest.mark.parametrize('model,scope_factory,visible_for_accepted,visible_for_raises', [
    ('action', PlanFactory, [
        # accepted
        InstancesVisibleForMixin.VisibleFor.PUBLIC,
        InstancesVisibleForMixin.VisibleFor.AUTHENTICATED,
        InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS,
        InstancesVisibleForMixin.VisibleFor.MODERATORS,
        InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
    ], [
        # raises
        # [never]
    ]),
    ('category', CategoryTypeFactory, [
        # accepted
        InstancesVisibleForMixin.VisibleFor.PUBLIC,
        InstancesVisibleForMixin.VisibleFor.AUTHENTICATED,
        InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
    ], [
        # raises
        InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS,
        InstancesVisibleForMixin.VisibleFor.MODERATORS,
    ]),
])
def test_attribute_type_visibility_validation(model, scope_factory, visible_for_accepted, visible_for_raises):
    scope = scope_factory()
    for visible_for in visible_for_accepted:
        AttributeTypeFactory(
           object_content_type=ContentType.objects.get(app_label='actions', model=model),
           scope=scope,
           instances_visible_for=visible_for,
        ).full_clean()
    for visible_for in visible_for_raises:
        with pytest.raises(ValidationError):
            AttributeTypeFactory(
               object_content_type=ContentType.objects.get(app_label='actions', model=model),
               scope=scope,
               instances_visible_for=visible_for,
            ).full_clean()


def test_attribute_type_visibility_contact_person_particular_action(plan, action, person):
    ac = ActionContactFactory(action__plan=plan, person=person, role=ActionContactPerson.Role.MODERATOR)
    assert ac.action != action
    assert not action.contact_persons.exists()
    at = AttributeTypeFactory(
        object_content_type=ContentType.objects.get_for_model(Action),
        scope=plan,
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS,
    )
    # Attribute for an action that `person` is a contact person for
    visible_attr = AttributeTextFactory(
        type=at,
        content_object=ac.action,
    )
    # Attribute for an action that `person` is not a contact person for
    invisible_attr = AttributeTextFactory(
        type=at,
        content_object=action,
    )
    assert visible_attr.is_visible_for_user(person.user, plan)
    # For InstancesVisibleForMixin.VisibleFor.CONTACT_PERSONS, it should not enough to be a contact person for *any*
    # action; you need to be a contact person of that particular action.
    assert not invisible_attr.is_visible_for_user(person.user, plan)


LANGUAGES_TO_TEST = [l[0] for l in settings.LANGUAGES]


@pytest.mark.parametrize('primary_language', LANGUAGES_TO_TEST)
@pytest.mark.parametrize('active_language', LANGUAGES_TO_TEST)
def test_action_i18n_when_saving(plan, action_factory, primary_language, active_language):
    plan.primary_language = primary_language
    plan.save()
    with translation.override(active_language):
        action = action_factory(plan=plan)
        action.name = 'action.name'
        action.save()
        assert action.i18n == None or len(action.i18n) == 0
        assert action.name == 'action.name'
        action.name = 'action.name.original'
        action.name_i18n = 'action.name_i18n'
        action.save()
        active_lang_translation_without_fallback = getattr(
            action,
            f"name_{active_language.replace('-', '_').lower()}"
        )
        if active_language == primary_language:
            assert action.name == 'action.name_i18n'
            assert not action.i18n
        else:
            assert active_lang_translation_without_fallback == 'action.name_i18n'
            assert action.name == 'action.name.original'
            assert len(action.i18n) > 0
