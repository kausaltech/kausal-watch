from __future__ import annotations

from datetime import date

from django.urls import reverse

import pytest

from actions.tests.factories import CategoryFactory, CategoryTypeFactory
from indicators.tests.factories import CommonIndicatorNormalizatorFactory, IndicatorContactFactory, IndicatorFactory

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



def test_update_contact_persons(api_client, plan, plan_admin_user, indicator):
    contact1 = IndicatorContactFactory()
    contact2 = IndicatorContactFactory()

    api_client.force_login(plan_admin_user)
    url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
    data = {
        "name": indicator.name,
        "unit": indicator.unit.id,
        "organization": indicator.organization.id,
        "contact_persons": [
            {"person": contact1.person.id},
            {"person": contact2.person.id},
        ],
    }

    response = api_client.put(url, data)
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.contact_persons.count() == 2
    assert set(indicator.contact_persons.values_list('person_id', flat=True)) == {contact1.person.id, contact2.person.id}


def test_update_categories(api_client, plan, plan_admin_user, indicator):

    category_type = CategoryTypeFactory(
        plan=plan,
        usable_for_indicators=True,
        editable_for_indicators=True,
        select_widget='multiple')
    category1 = CategoryFactory(type=category_type)
    category2 = CategoryFactory(type=category_type)

    url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    data = {
        "name": indicator.name,
        "unit": indicator.unit.id,
        "organization": indicator.organization.id,
        'categories': {
            category_type.identifier: [category1.id, category2.id],
        },
    }

    api_client.force_login(plan_admin_user)
    response = api_client.put(url, data)
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.categories.count() == 2
    assert set(indicator.categories.values_list('id', flat=True)) == {category1.id, category2.id}


def test_update_single_select_category(api_client, plan, plan_admin_user, indicator):
    category_type = CategoryTypeFactory(
        plan=plan,
        usable_for_indicators=True,
        editable_for_indicators=True,
        select_widget='single')
    category = CategoryFactory(type=category_type)

    url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
    data = {
        "name": indicator.name,
        "unit": indicator.unit.id,
        "organization": indicator.organization.id,
        'categories': {
            category_type.identifier: category.id,
        },
    }

    api_client.force_login(plan_admin_user)
    response = api_client.put(url, data)
    assert response.status_code == 200

    indicator.refresh_from_db()
    assert indicator.categories.count() == 1
    assert indicator.categories.first().id == category.id


def test_update_categories_invalid_type(api_client, plan, plan_admin_user, indicator):
    category_type = CategoryTypeFactory(plan=plan, usable_for_indicators=False, select_widget='single')
    category = CategoryFactory(type=category_type)

    url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})
    data = {
        'categories': {
            category_type.identifier: [category.id],
        },
    }

    api_client.force_login(plan_admin_user)
    response = api_client.put(url, data)
    assert response.status_code == 400


def test_get_indicator_with_categories(api_client, plan, plan_admin_user, indicator):

    category_type = CategoryTypeFactory(plan=plan, usable_for_indicators=True)
    category = CategoryFactory(type=category_type)
    indicator.categories.add(category)

    url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    api_client.force_login(plan_admin_user)
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data['categories'][category_type.identifier] == category.id


def test_get_indicator_with_contact_persons(api_client, plan, plan_admin_user, indicator):
    contact = IndicatorContactFactory(indicator=indicator)

    url = reverse('indicator-detail', kwargs={'plan_pk': plan.pk, 'pk': indicator.pk})

    api_client.force_login(plan_admin_user)
    response = api_client.get(url)
    assert response.status_code == 200
    assert response.data['contact_persons'] == [{'person': contact.person.id}]
