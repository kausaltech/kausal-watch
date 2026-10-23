from __future__ import annotations

import json

from django.urls import reverse

import pytest

from actions.models import Pledge
from actions.pledge_admin import PledgeAdminForm, PledgeViewSet
from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory

pytestmark = pytest.mark.django_db


def _autocomplete(client, **forward):
    response = client.get(reverse('action-autocomplete'), {'forward': json.dumps(forward)})
    assert response.status_code == 200
    return [result['text'] for result in response.json()['results']]


@pytest.fixture
def umbrella_plan(plan):
    """Make the admin's plan an umbrella plan with two child plans and an explicitly related plan."""
    plan.related_plans.add(PlanFactory.create(name='Related'))
    for name in ('Child A', 'Child B'):
        PlanFactory.create(name=name, short_name=name, parent=plan)
    return plan


class TestChildPlanActionsAutocomplete:
    def test_umbrella_plan_offers_its_own_and_its_child_plans_actions(self, umbrella_plan, plan_admin_user, client):
        own = ActionFactory.create(plan=umbrella_plan)
        child_a, child_b = (ActionFactory.create(plan=child) for child in umbrella_plan.children.order_by('name'))
        ActionFactory.create(plan=umbrella_plan.related_plans.get())
        client.force_login(plan_admin_user)

        labels = _autocomplete(client, child_plans=True)

        # Child plan actions are labelled with their plan; the umbrella plan's own are not
        assert sorted(labels) == sorted([str(own), f'Child A: {child_a}', f'Child B: {child_b}'])

    def test_child_plan_offers_only_its_own_actions(self, umbrella_plan, plan_admin_user, client):
        child_a, child_b = umbrella_plan.children.order_by('name')
        ActionFactory.create(plan=umbrella_plan)
        own = ActionFactory.create(plan=child_a)
        ActionFactory.create(plan=child_b)
        client.force_login(plan_admin_user)

        labels = _autocomplete(client, child_plans=True, plan=child_a.pk)

        assert labels == [str(own)]


class TestPledgeActionChoices:
    def test_umbrella_plan_pledge_accepts_child_plan_actions(self, umbrella_plan):
        own = ActionFactory.create(plan=umbrella_plan)
        child_actions = [ActionFactory.create(plan=child) for child in umbrella_plan.children.all()]
        unrelated = ActionFactory.create(plan=umbrella_plan.related_plans.get())

        form = PledgeAdminForm(plan=umbrella_plan, instance=Pledge(plan=umbrella_plan))

        choices = set(form.fields['actions'].queryset)  # type: ignore[attr-defined]
        assert choices == {own, *child_actions}
        assert unrelated not in choices

    def test_pledge_picker_asks_for_child_plan_actions(self, plan, plan_admin_user, client):
        ClientPlanFactory.create(plan=plan)
        plan.features.enable_community_engagement = True
        plan.features.save()
        client.force_login(plan_admin_user)

        response = client.get(reverse(PledgeViewSet().get_url_name('add')))

        assert response.status_code == 200
        assert 'child_plans' in response.content.decode('utf-8')
