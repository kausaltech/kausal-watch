from __future__ import annotations

from typing import TYPE_CHECKING, cast

from django.core.exceptions import ValidationError
from django.urls import reverse

import pytest

from actions.models import Pledge
from actions.tests.factories import PlanFactory
from actions.wagtail_admin import PlanViewSet
from admin_site.tests.factories import ClientFactory, ClientPlanFactory
from copying.main import copy_plan

if TYPE_CHECKING:
    from django import forms
    from wagtail.fields import RichTextField

pytestmark = pytest.mark.django_db


PLEDGE_FEEDBACK_ENABLED_QUERY = """
    query($plan: ID!) {
        plan(id: $plan) {
            pledgeFeedbackEnabled
        }
    }
"""


def _create_engagement_plan(**kwargs):
    plan = PlanFactory.create(primary_client=ClientFactory.create(), **kwargs)
    plan.features.enable_community_engagement = True
    plan.features.save()
    return plan


class TestPledgeFeedbackEnabledQuery:
    def _query(self, graphql_client_query_data, plan) -> bool:
        data = graphql_client_query_data(PLEDGE_FEEDBACK_ENABLED_QUERY, variables={'plan': plan.identifier})
        return data['plan']['pledgeFeedbackEnabled']

    def test_feedback_is_asked_for_by_default(self, graphql_client_query_data):
        plan = _create_engagement_plan()

        assert self._query(graphql_client_query_data, plan) is True

    def test_feedback_can_be_turned_off(self, graphql_client_query_data):
        plan = _create_engagement_plan()
        plan.pledge_feedback_enabled = False
        plan.save()

        assert self._query(graphql_client_query_data, plan) is False


def test_setting_is_editable_by_plan_admins_on_the_community_engagement_tab(plan, plan_admin_user, client):
    ClientPlanFactory.create(plan=plan)
    plan.features.enable_community_engagement = True
    plan.features.save()
    client.force_login(plan_admin_user)

    response = client.get(reverse(PlanViewSet().get_url_name('edit'), args=[plan.pk]))

    assert response.status_code == 200
    assert 'name="pledge_feedback_enabled"' in response.content.decode('utf-8')


def test_copying_a_plan_keeps_its_pledge_feedback_setting(plan_with_pages):
    plan_with_pages.pledge_feedback_enabled = False
    plan_with_pages.save()

    plan_copy = copy_plan(plan_with_pages)

    assert plan_copy.pledge_feedback_enabled is False


def _form_field(field_name: str) -> forms.Field:
    model_field = cast('RichTextField', Pledge._meta.get_field(field_name))
    return cast('forms.Field', model_field.formfield())


@pytest.mark.parametrize('field_name', ['impact_statement', 'local_equivalency'])
class TestImpactTextLength:
    """The admin form limits the text, not counting HTML tags."""

    def test_250_characters_are_allowed(self, field_name):
        _form_field(field_name).clean('<p>' + 'a' * 250 + '</p>')

    def test_more_than_250_characters_are_refused(self, field_name):
        with pytest.raises(ValidationError):
            _form_field(field_name).clean('<p>' + 'a' * 251 + '</p>')
