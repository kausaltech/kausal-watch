import pytest
from actions.models import ActionSchedule


@pytest.mark.django_db
def test_plan_api_get(api_client, plan_list_url, plan):
    response = api_client.get(plan_list_url)
    data = response.json_data
    assert data['meta']['pagination']['count'] == 1
    assert len(data['data']) == 1

    obj = data['data'][0]
    attr = obj['attributes']
    assert attr['name'] == plan.name
    assert attr['identifier'] == plan.identifier
    assert attr['image_url'] is None

    schedule = ActionSchedule.objects.create(
        plan=plan, name='next year', begins_at='2019-01-01', ends_at='2019-12-31'
    )

    response = api_client.get(
        plan_list_url,
        data={'include': 'action_schedules'}
    )
    data = response.json_data
    assert len(data['data']) == 1
    assert len(data['included']) == 1
    assert data['included'][0]['attributes']['name'] == schedule.name
    assert data['included'][0]['id'] == str(schedule.id)


@pytest.mark.django_db
def test_action_api_get(api_client, action_list_url, action):
    response = api_client.get(action_list_url, data=dict(include='plan'))
    data = response.json_data
    assert data['meta']['pagination']['count'] == 1
    assert len(data['data']) == 1

    obj = data['data'][0]
    assert obj['attributes']['name'] == action.name
    assert obj['attributes']['identifier'] == action.identifier
    plan = data['included'][0]
    assert plan['id'] == str(action.plan_id)
    assert plan['attributes']['name'] == action.plan.name
