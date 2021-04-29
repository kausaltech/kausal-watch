import pytest
from datetime import date
from django.urls import reverse

from indicators.tests.factories import IndicatorFactory

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


@pytest.fixture
def post_values(client, plan_admin_user):
    client.force_login(plan_admin_user)

    def post(indicator, data):
        edit_values_url = reverse('indicator-values', kwargs={'pk': indicator.id})
        response = client.post(edit_values_url, data, content_type='application/json')
        assert response.status_code == 200
        indicator.refresh_from_db()

    return post


def test_add_first_value_updates_indicator_latest_value(post_values):
    indicator = IndicatorFactory()
    assert not indicator.values.exists()
    assert indicator.latest_value is None
    post_values(indicator, [VALUE_2019])
    assert not indicator.latest_value.categories.exists()
    assert indicator.latest_value.date == date(2019, 12, 31)
    assert indicator.latest_value.value == VALUE_2019['value']


def test_add_value_updates_indicator_latest_value(post_values):
    indicator = IndicatorFactory()
    post_values(indicator, [VALUE_2019])

    post_values(indicator, [VALUE_2020])
    assert not indicator.latest_value.categories.exists()
    assert indicator.latest_value.date == date(2020, 12, 31)
    assert indicator.latest_value.value == VALUE_2020['value']


def test_add_value_keeps_null_due_date(post_values):
    indicator = IndicatorFactory()
    post_values(indicator, [VALUE_2019])
    assert indicator.updated_values_due_at is None


def test_add_value_updates_due_date(post_values):
    indicator = IndicatorFactory(updated_values_due_at=date(2020, 3, 1))
    post_values(indicator, [VALUE_2019])
    assert indicator.updated_values_due_at == date(2021, 3, 1)
