import pytest

pytestmark = pytest.mark.django_db


def test_plan_api_get(api_client, plan_list_url, plan):
    response = api_client.get(plan_list_url)
    data = response.json_data
    assert data['count'] == 1
    assert len(data['results']) == 1

    obj = data['results'][0]
    assert obj['name'] == plan.name
    assert obj['identifier'] == plan.identifier
    # assert obj['image_url'] is None

    """
    schedule = ActionSchedule.objects.create(
        plan=plan, name='next year', begins_at='2019-01-01', ends_at='2019-12-31'
    )

    response = api_client.get(
        plan_list_url,
        data={'include': 'action_schedules'}
    )
    data = response.json_data
    assert data['count'] == 1
    assert len(data['included']) == 1
    assert data['included'][0]['attributes']['name'] == schedule.name
    assert data['included'][0]['id'] == str(schedule.id)
    """


def test_action_api_get(api_client, action_list_url, action):
    response = api_client.get(action_list_url)
    data = response.json_data
    assert data['count'] == 1
    assert len(data['results']) == 1

    obj = data['results'][0]
    assert obj['name'] == action.name
    assert obj['identifier'] == action.identifier
    assert obj['plan'] == action.plan_id
