import itertools

import pytest


pytestmark = pytest.mark.django_db
OVERRIDE_COLOR = 'beige123'


@pytest.fixture(params=[True, False], ids=['override_status_color', 'default_status_color'])
def colorized_statuses(request, plan, action_status_factory):
    should_override_color = request.param
    color = OVERRIDE_COLOR if should_override_color else None
    return [action_status_factory(plan=plan, identifier=f'status{i}', color=color) for i in range(0, 5)]


@pytest.fixture(params=[True, False], ids=['override_phase_color', 'default_phase_color'])
def colorized_implementation_phases(request, plan, action_implementation_phase_factory):
    should_override_color = request.param
    color = OVERRIDE_COLOR if should_override_color else None
    return [action_implementation_phase_factory(plan=plan, identifier=f'phase{i}', color=color) for i in range(0, 5)]


@pytest.fixture
def plan_with_statuses_phases_and_actions(
    plan,
    action_factory
):
    statuses = [None] + list(plan.action_statuses.all())
    phases = [None] + list(plan.action_implementation_phases.all())
    combinations = itertools.product(statuses, phases)
    for s, p in combinations:
        action_factory(plan=plan, status=s, implementation_phase=p)
    return plan


def test_plan_action_colors(
        graphql_client_query_data,
        colorized_statuses,
        colorized_implementation_phases,
        plan_with_statuses_phases_and_actions,
        django_assert_max_num_queries
):
    plan = plan_with_statuses_phases_and_actions
    data = None
    with django_assert_max_num_queries(7):
        data = graphql_client_query_data(
            '''
            query($plan: ID!) {
                plan(id: $plan) {
                    id
                    actions { id, color }
                }
            }
            ''',
            variables=dict(plan=plan.identifier)
        )
    assert data['plan']['id'] == plan.identifier
    assert plan.action_statuses.count() > 0
    assert plan.action_implementation_phases.count() > 0
    assert len(data['plan']['actions']) > 0
    for action in data['plan']['actions']:
        assert action['color'] in [OVERRIDE_COLOR, 'grey010']


def test_plan_phase_colors(
        graphql_client_query_data,
        plan,
        colorized_implementation_phases,
        django_assert_max_num_queries
):
    data = None
    with django_assert_max_num_queries(4):
        data = graphql_client_query_data(
            '''
            query($plan: ID!) {
                plan(id: $plan) {
                    actionImplementationPhases { identifier, color }
                }
            }
            ''',
            variables=dict(plan=plan.identifier)
        )
    assert len(data['plan']['actionImplementationPhases']) == len(colorized_implementation_phases)
    for phase in data['plan']['actionImplementationPhases']:
        result_color = phase['color']
        corresponding_phase = next(
            p for p in colorized_implementation_phases if p.identifier == phase['identifier']
        )
        if corresponding_phase.color:
            assert result_color == OVERRIDE_COLOR
        else:
            assert result_color is None


def test_plan_status_colors(
        graphql_client_query_data,
        plan,
        colorized_statuses,
        django_assert_max_num_queries
):
    data = None
    with django_assert_max_num_queries(6):
        data = graphql_client_query_data(
            '''
            query($plan: ID!) {
                plan(id: $plan) {
                    actionStatuses { identifier, color }
                }
            }
            ''',
            variables=dict(plan=plan.identifier)
        )
    assert len(data['plan']['actionStatuses']) == len(colorized_statuses)
    for status in data['plan']['actionStatuses']:
        result_color = status['color']
        corresponding_status = next(
            p for p in colorized_statuses if p.identifier == status['identifier']
        )
        assert result_color is not None
        if corresponding_status.color:
            assert result_color == OVERRIDE_COLOR
