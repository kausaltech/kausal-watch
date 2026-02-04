from __future__ import annotations

from datetime import date

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest

from actions.tests.factories import CategoryFactory, CategoryTypeFactory
from actions.tests.utils import assert_log_entry_created, count_log_entries
from audit_logging.models import PlanScopedModelLogEntry
from indicators.models import Indicator
from indicators.tests.factories import CommonIndicatorNormalizatorFactory, IndicatorContactFactory, IndicatorFactory
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

VALUE_2019 = {
    'categories': [],
    'date': '2019-12-31',
    'value': 1.23,
}
VALUE_2020 = {
    'categories': [],
    'date': '2020-12-31',
    'value': 0.12,
}
VALUE_2021 = {
    'categories': [],
    'date': '2021-12-31',
    'value': 0.1,
}
VALUE_2022 = {
    'categories': [],
    'date': '2022-12-31',
    'value': 0.2,
}
GOAL_2030 = {
    'date': '2030-01-01',
    'value': 0.01,
}
GOAL_2045 = {
    'date': '2045-01-01',
    'value': 0.001,
}
GOAL_2035 = {
    'date': '2035-01-01',
    'value': 0.01,
}
GOAL_2040 = {
    'date': '2040-01-01',
    'value': 0.001,
}


def _do_post(path, client, plan, indicator, data):
    edit_url = reverse(path, kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
    response = client.post(edit_url, data, content_type='application/json')
    indicator.refresh_from_db()
    return response


def post(client, plan, user, path, indicator, data, expected_status_code=200):
    if user is not None:
        client.force_login(user)
    response = _do_post(path, client, plan, indicator, data)
    assert response.status_code == expected_status_code
    client.logout()
    return expected_status_code == 200


def assert_db_matches_set(related_field, values):
    in_db_values = set(related_field.values_list('date', 'value'))
    assert in_db_values == set(
        ((date.fromisoformat(v['date']), v['value']) for v in values),
    )


def assert_values_match(indicator, values):
    assert_db_matches_set(indicator.values, values)


def assert_goals_match(indicator, goals):
    assert_db_matches_set(indicator.goals, goals)


def test_all_values_get_replaced(client, plan, plan_admin_user):
    indicator = IndicatorFactory(plans=[plan])
    assert not indicator.values.exists()
    for values in [[VALUE_2019, VALUE_2020], [VALUE_2021, VALUE_2022]]:
        # post_values(indicator, values)
        post(client, plan, plan_admin_user, 'indicator-values', indicator, values)
        assert_values_match(indicator, values)


def test_all_goals_get_replaced(client, plan, plan_admin_user):
    indicator = IndicatorFactory(plans=[plan])
    assert not indicator.goals.exists()
    for values in [[GOAL_2030, GOAL_2045], [GOAL_2035, GOAL_2040]]:
        post(client, plan, plan_admin_user, 'indicator-goals', indicator, values)
        assert_goals_match(indicator, values)


@pytest.mark.parametrize("reverse_request_order", [False, True])
@pytest.mark.parametrize("test_goals_instead", [False, True])
def test_values_get_normalized(client, plan, plan_admin_user, reverse_request_order, test_goals_instead):
    # Normalize emissions by population
    emissions = IndicatorFactory(plans=[plan])
    population = IndicatorFactory(plans=[plan], organization=emissions.organization)
    normalizator = CommonIndicatorNormalizatorFactory(
        normalizable=emissions.common,
        normalizer=population.common,
    )
    emissions_value = {
        'categories': [],
        'date': '2019-12-31',
        'value': 1,
    }
    population_value = {
        'categories': [],
        'date': '2019-12-31',
        'value': 2,
    }
    # It shouldn't matter whether we first update the normalizable or the normalizer
    request_data = [(population, [population_value]), (emissions, [emissions_value])]
    if reverse_request_order:
        request_data.reverse()
    path = 'indicator-values'
    if test_goals_instead:
        path = 'indicator-goals'
        del emissions_value['categories']
        del population_value['categories']
    for indicator, values in request_data:
        post(client, plan, plan_admin_user, path, indicator, values)
    expected_value = emissions_value['value'] / population_value['value'] * normalizator.unit_multiplier
    expected = [{str(population.common.id): expected_value}]
    if test_goals_instead:
        result = list(emissions.goals.values_list('normalized_values', flat=True))
    else:
        result = list(emissions.values.values_list('normalized_values', flat=True))
    assert result == expected


# TODO: these authorization test turned out difficult to implement
#       without flakiness.
# def test_contact_person_unauthorized(client, plan, action_contact_person_user):
#     indicator = IndicatorFactory(plans=[plan])
#     assert not indicator.values.exists()
#     values = [VALUE_2019, VALUE_2020]
#     post(client, plan, action_contact_person_user, 'indicator-values', indicator, values, expected_status_code=403)
#     assert not indicator.values.exists()


# def test_unauthorized_without_login(client, plan):
#     indicator = IndicatorFactory(plans=[plan])
#     assert not indicator.values.exists()
#     values = [VALUE_2019, VALUE_2020]
#     post(client, plan, None, 'indicator-values', indicator, values, expected_status_code=401)
#     assert not indicator.values.exists()


# def test_contact_person_goals_unauthorized(client, plan, action_contact_person_user):
#     indicator = IndicatorFactory(plans=[plan])
#     assert not indicator.goals.exists()
#     values = [GOAL_2030, GOAL_2045]
#     post(client, plan, action_contact_person_user, 'indicator-goals', indicator, values, expected_status_code=403)
#     assert not indicator.goals.exists()


# def test_goals_unauthorized_without_login(client, plan, post_goals_no_user):
#     indicator = IndicatorFactory(plans=[plan])
#     assert not indicator.goals.exists()
#     values = [GOAL_2030, GOAL_2045]
#     post(client, plan, None, 'indicator-goals', indicator, values, expected_status_code=401)
#     assert not indicator.goals.exists()


def test_add_first_value_updates_indicator_latest_value(client, plan, plan_admin_user):
    indicator = IndicatorFactory(plans=[plan])
    assert not indicator.values.exists()
    assert indicator.latest_value is None
    post(client, plan, plan_admin_user, 'indicator-values', indicator, [VALUE_2019])
    assert not indicator.latest_value.categories.exists()
    assert indicator.latest_value.date == date(2019, 12, 31)
    assert indicator.latest_value.value == VALUE_2019['value']


def test_add_value_updates_indicator_latest_value(client, plan, plan_admin_user):
    indicator = IndicatorFactory(plans=[plan])
    post(client, plan, plan_admin_user, 'indicator-values', indicator, [VALUE_2019])
    post(client, plan, plan_admin_user, 'indicator-values', indicator, [VALUE_2020])
    assert not indicator.latest_value.categories.exists()
    assert indicator.latest_value.date == date(2020, 12, 31)
    assert indicator.latest_value.value == VALUE_2020['value']


def test_add_value_keeps_null_due_date(client, plan, plan_admin_user):
    indicator = IndicatorFactory(plans=[plan])
    post(client, plan, plan_admin_user, 'indicator-values', indicator, [VALUE_2019])
    assert indicator.updated_values_due_at is None


def test_add_value_updates_due_date(client, plan, plan_admin_user):
    indicator = IndicatorFactory(plans=[plan], updated_values_due_at=date(2020, 3, 1))
    post(client, plan, plan_admin_user, 'indicator-values', indicator, [VALUE_2019])
    assert indicator.updated_values_due_at == date(2021, 3, 1)



def test_update_contact_persons(api_client, plan, plan_admin_user, indicator, indicator_detail_url):
    person1 = PersonFactory.create()
    person2 = PersonFactory.create()

    api_client.force_login(plan_admin_user)
    data = {
        "name": indicator.name,
        "unit": indicator.unit.id,
        "organization": indicator.organization.id,
        "contact_persons": [
            {"person": person1.id},
            {"person": person2.id},
        ],
    }

    response = api_client.put(indicator_detail_url, data)
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.contact_persons.count() == 2
    assert set(indicator.contact_persons.values_list('person_id', flat=True)) == {person1.id, person2.id}


def test_update_categories(api_client, plan, plan_admin_user, indicator, indicator_detail_url):

    category_type = CategoryTypeFactory(
        plan=plan,
        usable_for_indicators=True,
        editable_for_indicators=True,
        select_widget='multiple')
    category1 = CategoryFactory(type=category_type)
    category2 = CategoryFactory(type=category_type)

    data = {
        "name": indicator.name,
        "unit": indicator.unit.id,
        "organization": indicator.organization.id,
        'categories': {
            category_type.identifier: [category1.id, category2.id],
        },
    }

    api_client.force_login(plan_admin_user)
    response = api_client.put(indicator_detail_url, data)
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.categories.count() == 2
    assert set(indicator.categories.values_list('id', flat=True)) == {category1.id, category2.id}


def test_update_single_select_category(api_client, plan, plan_admin_user, indicator, indicator_detail_url):
    category_type = CategoryTypeFactory(
        plan=plan,
        usable_for_indicators=True,
        editable_for_indicators=True,
        select_widget='single')
    category = CategoryFactory(type=category_type)

    data = {
        "name": indicator.name,
        "unit": indicator.unit.id,
        "organization": indicator.organization.id,
        'categories': {
            category_type.identifier: category.id,
        },
    }

    api_client.force_login(plan_admin_user)
    response = api_client.put(indicator_detail_url, data)
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.categories.count() == 1
    assert indicator.categories.first().id == category.id


def test_update_categories_invalid_type(api_client, plan, plan_admin_user, indicator_detail_url):
    category_type = CategoryTypeFactory(plan=plan, usable_for_indicators=False, select_widget='single')
    category = CategoryFactory(type=category_type)

    data = {
        'categories': {
            category_type.identifier: [category.id],
        },
    }

    api_client.force_login(plan_admin_user)
    response = api_client.put(indicator_detail_url, data)
    assert response.status_code == 400


def test_get_indicator_with_categories(api_client, plan, plan_admin_user, indicator, indicator_detail_url):
    category_type = CategoryTypeFactory(plan=plan, usable_for_indicators=True)
    category = CategoryFactory(type=category_type)
    indicator.categories.add(category)
    indicator.save()

    api_client.force_login(plan_admin_user)
    response = api_client.get(indicator_detail_url)
    assert response.status_code == 200
    assert response.data['categories'][category_type.identifier] == category.id


def test_get_indicator_with_contact_persons(api_client, plan_admin_user, indicator, indicator_detail_url):
    contact = IndicatorContactFactory(indicator=indicator)

    api_client.force_login(plan_admin_user)
    response = api_client.get(indicator_detail_url)
    assert response.status_code == 200
    assert response.data['contact_persons'] == [{'person': contact.person.id}]


def test_bulk_update_indicator_without_permissions(api_client, plan, indicator_list_url):
    indicator1 = IndicatorFactory.create(plans=[plan], organization=plan.organization)
    indicator2 = IndicatorFactory.create(plans=[plan], organization=plan.organization)
    contact = IndicatorContactFactory.create(indicator=indicator1)

    # User in contact will try to modify indicator2, which they do not have permissions for
    api_client.force_login(contact.person.user)
    data = [{
        'id': indicator2.id,
        'name': f'updated {indicator2.name}',
        'unit': indicator2.unit.pk,
        'organization': indicator2.organization.id,
    }]

    response = api_client.put(indicator_list_url, data)
    assert response.status_code == 403

    old_name = indicator2.name
    indicator2.refresh_from_db()
    assert indicator2.name == old_name


def test_indicator_post_creates_log_entry(
        api_client, plan, indicator_list_url, person_factory, unit_factory, organization_factory):
    """Test that creating an indicator creates a PlanScopedModelLogEntry with action='wagtail.create'."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    unit = unit_factory()
    org = organization_factory()
    org.related_plans.add(plan)

    response = api_client.post(indicator_list_url, data={
        'name': 'Test Indicator',
        'unit': unit.pk,
        'organization': org.pk,
    })
    assert response.status_code == 201

    created_indicator = Indicator.objects.get(name='Test Indicator')
    assert_log_entry_created(created_indicator, 'wagtail.create', admin_person.user, plan)


def test_indicator_put_creates_log_entry(
        api_client, plan, plan_admin_user, indicator, indicator_detail_url):
    """Test that updating an indicator creates a PlanScopedModelLogEntry with action='wagtail.edit'."""
    api_client.force_login(plan_admin_user)

    response = api_client.put(indicator_detail_url, data={
        'name': 'Updated Indicator',
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
    })
    assert response.status_code == 200

    assert_log_entry_created(indicator, 'wagtail.edit', plan_admin_user, plan)


def test_indicator_delete_creates_log_entry(
        api_client, plan, plan_admin_user, indicator_factory):
    """Test that deleting an indicator creates a PlanScopedModelLogEntry with action='wagtail.delete'."""
    api_client.force_login(plan_admin_user)

    assert plan.pk == plan_admin_user.person.general_admin_plans.first().pk

    indicator = indicator_factory(plans=[plan], organization=plan.organization)
    indicator_pk = indicator.pk
    indicator_detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    response = api_client.delete(indicator_detail_url)
    assert response.status_code == 204

    assert not Indicator.objects.filter(pk=indicator_pk).exists()

    content_type = ContentType.objects.get_for_model(Indicator, for_concrete_model=False)
    log_entry = PlanScopedModelLogEntry.objects.filter(
        content_type=content_type,
        object_id=str(indicator_pk),
        action='wagtail.delete',
        plan=plan
    ).first()
    assert log_entry is not None, f"Expected log entry for deleted indicator {indicator_pk}"
    assert log_entry.user_id == plan_admin_user.pk


def test_bulk_indicator_post_creates_individual_log_entries(
        api_client, plan, indicator_list_url, person_factory, unit_factory, organization_factory):
    """Test that bulk POST of indicators creates individual PlanScopedModelLogEntry for each indicator."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    unit = unit_factory()
    org = organization_factory()
    org.related_plans.add(plan)

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()

    response = api_client.post(indicator_list_url, data=[
        {'name': 'Indicator 1', 'unit': unit.pk, 'organization': org.pk},
        {'name': 'Indicator 2', 'unit': unit.pk, 'organization': org.pk},
        {'name': 'Indicator 3', 'unit': unit.pk, 'organization': org.pk},
    ])
    assert response.status_code == 201

    assert Indicator.objects.filter(name__startswith='Indicator ').count() >= 3

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.create').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries, got {final_log_count - initial_log_count}"


def test_bulk_indicator_put_creates_individual_log_entries(
        api_client, plan, indicator_list_url, person_factory, indicator_factory):
    """Test that bulk PUT of indicators creates individual PlanScopedModelLogEntry for each indicator."""
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    indicators = [
        indicator_factory(plans=[plan], organization=plan.organization, name=f'Original Indicator {i}')
        for i in range(1, 4)
    ]

    initial_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()

    data = [{
            'id': indicator.id,
            'uuid': indicator.uuid,
            'name': f'Updated {indicator.name}',
            'unit': indicator.unit.pk,
            'organization': indicator.organization.pk,
           } for indicator in indicators
    ]

    response = api_client.put(indicator_list_url, data=data)
    assert response.status_code == 200

    final_log_count = PlanScopedModelLogEntry.objects.filter(plan=plan, action='wagtail.edit').count()
    assert final_log_count == initial_log_count + 3, \
        f"Expected 3 new log entries for bulk update, got {final_log_count - initial_log_count}"

    for indicator in indicators:
        total_logs = count_log_entries(instance=indicator, plan=plan)
        assert total_logs >= 1, f"Expected at least 1 log entry for indicator {indicator.name}"


def test_get_indicator_returns_level_for_plan(api_client, plan, plan_admin_user, indicator_factory):
    indicator = indicator_factory(plans=[])
    indicator.levels.create(plan=plan, level='strategic')
    indicator.organization.related_plans.add(plan)
    detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    api_client.force_login(plan_admin_user)
    response = api_client.get(detail_url)
    assert response.status_code == 200
    assert 'level' in response.data
    assert response.data['level'] == 'strategic'


def test_get_indicator_returns_null_level_when_no_level_exists(
        api_client, plan, plan_admin_user, indicator_factory, unit_factory, organization_factory):
    indicator = indicator_factory(plans=[])
    indicator.organization.related_plans.add(plan)
    detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    api_client.force_login(plan_admin_user)
    response = api_client.get(detail_url)
    assert response.status_code == 200
    assert response.data['level'] is None


def test_create_indicator_sets_strategic_level(
        api_client, plan, person_factory, unit_factory, organization_factory, indicator_list_url):
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    unit = unit_factory()
    org = organization_factory()
    org.related_plans.add(plan)

    response = api_client.post(indicator_list_url, data={
        'name': 'New Indicator',
        'unit': unit.pk,
        'organization': org.pk,
    })
    assert response.status_code == 201

    created_indicator = Indicator.objects.get(name='New Indicator')
    assert created_indicator.levels.count() == 1
    level = created_indicator.levels.first()
    assert level is not None
    assert level.plan == plan
    assert level.level == 'strategic'


def test_create_indicator_with_custom_level(
        api_client, plan, person_factory, unit_factory, organization_factory, indicator_list_url):
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    unit = unit_factory()
    org = organization_factory()
    org.related_plans.add(plan)

    response = api_client.post(indicator_list_url, data={
        'name': 'Tactical Indicator',
        'unit': unit.pk,
        'organization': org.pk,
        'level': 'tactical',
    })
    assert response.status_code == 201

    created_indicator = Indicator.objects.get(name='Tactical Indicator')
    assert created_indicator.levels.count() == 1
    level = created_indicator.levels.first()
    assert level is not None
    assert level.plan == plan
    assert level.level == 'tactical'


def test_create_indicator_with_null_level_creates_no_level(
        api_client, plan, person_factory, unit_factory, organization_factory, indicator_list_url):
    admin_person = person_factory(general_admin_plans=[plan])
    api_client.force_login(admin_person.user)

    unit = unit_factory()
    org = organization_factory()
    org.related_plans.add(plan)

    response = api_client.post(indicator_list_url, data={
        'name': 'No Level Indicator',
        'unit': unit.pk,
        'organization': org.pk,
        'level': None,
    })
    assert response.status_code == 201

    created_indicator = Indicator.objects.get(name='No Level Indicator')
    assert created_indicator.levels.count() == 0


def test_update_indicator_level_changes_level(api_client, plan, plan_admin_user, indicator, indicator_detail_url):
    api_client.force_login(plan_admin_user)

    response = api_client.put(indicator_detail_url, data={
        'name': indicator.name,
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
        'level': 'tactical',
    })
    assert response.status_code == 200

    indicator.refresh_from_db()
    level = indicator.levels.get(plan=plan)
    assert level.level == 'tactical'


def test_update_indicator_level_to_null_removes_level(api_client, plan, plan_admin_user, indicator, indicator_detail_url):
    api_client.force_login(plan_admin_user)

    response = api_client.put(indicator_detail_url, data={
        'name': indicator.name,
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
        'level': None,
    })
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert not indicator.levels.filter(plan=plan).exists()


def test_update_indicator_adds_level_when_none_exists(
        api_client, plan, plan_admin_user, indicator_factory, indicator_contact_factory):
    indicator = indicator_factory(plans=[])
    indicator.organization.related_plans.add(plan)
    indicator_contact_factory(indicator=indicator, person=plan_admin_user.person)
    detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    api_client.force_login(plan_admin_user)

    assert not indicator.levels.filter(plan=plan).exists()

    response = api_client.put(detail_url, data={
        'name': indicator.name,
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
        'level': 'operational',
    })
    assert response.status_code == 200

    indicator.refresh_from_db()
    level = indicator.levels.get(plan=plan)
    assert level.level == 'operational'


def test_update_indicator_level_does_not_affect_other_plans(
        api_client, plan, plan_admin_user, indicator_factory, plan_factory):
    other_plan = plan_factory()
    indicator = indicator_factory(plans=[])
    indicator.organization.related_plans.add(plan)
    indicator.organization.related_plans.add(other_plan)
    indicator.levels.create(plan=plan, level='strategic')
    indicator.levels.create(plan=other_plan, level='tactical')

    detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
    api_client.force_login(plan_admin_user)

    response = api_client.put(detail_url, data={
        'name': indicator.name,
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
        'level': 'operational',
    })
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.levels.get(plan=plan).level == 'operational'
    assert indicator.levels.get(plan=other_plan).level == 'tactical'


def test_remove_indicator_level_does_not_affect_other_plans(
        api_client, plan, plan_admin_user, indicator_factory, plan_factory):
    other_plan = plan_factory()
    indicator = indicator_factory(plans=[])
    indicator.organization.related_plans.add(plan)
    indicator.organization.related_plans.add(other_plan)
    indicator.levels.create(plan=plan, level='strategic')
    indicator.levels.create(plan=other_plan, level='tactical')

    detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
    api_client.force_login(plan_admin_user)

    response = api_client.put(detail_url, data={
        'name': indicator.name,
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
        'level': None,
    })
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert not indicator.levels.filter(plan=plan).exists()
    assert indicator.levels.get(plan=other_plan).level == 'tactical'


def test_update_indicator_with_invalid_level_returns_400(
        api_client, plan, plan_admin_user, indicator_factory):
    indicator = indicator_factory(plans=[])
    indicator.levels.create(plan=plan, level='strategic')
    indicator.organization.related_plans.add(plan)
    detail_url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    api_client.force_login(plan_admin_user)

    response = api_client.put(detail_url, data={
        'name': indicator.name,
        'unit': indicator.unit.pk,
        'organization': indicator.organization.pk,
        'level': 'invalid_level',
    })
    assert response.status_code == 400
    assert 'level' in response.data
