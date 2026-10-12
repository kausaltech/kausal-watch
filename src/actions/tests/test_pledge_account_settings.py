from __future__ import annotations

from django.core.exceptions import ValidationError
from django.urls import reverse

import pytest

from actions.tests.factories import PlanFactory
from actions.wagtail_admin import PlanViewSet
from admin_site.tests.factories import ClientFactory, ClientPlanFactory
from copying.main import copy_plan

pytestmark = pytest.mark.django_db


PLEDGE_ACCOUNT_SETTINGS_QUERY = """
    query($plan: ID!, $lang: String!) @locale(lang: $lang) {
        plan(id: $plan) {
            pledgeTermsUrl
            pledgePrivacyUrl
            pledgeAccountTitle
            pledgeAccountDescription
            pledgeMarketingConsentLabel
        }
    }
"""


def _create_engagement_plan(**kwargs):
    plan = PlanFactory.create(primary_client=ClientFactory.create(), **kwargs)
    plan.features.enable_community_engagement = True
    plan.features.save()
    return plan


class TestPledgeAccountSettingsQuery:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = _create_engagement_plan(primary_language='en', other_languages=['fi'])

    def _query(self, graphql_client_query_data, lang: str):
        data = graphql_client_query_data(PLEDGE_ACCOUNT_SETTINGS_QUERY, variables={'plan': self.plan.identifier, 'lang': lang})
        return data['plan']

    def test_empty_settings_are_null(self, graphql_client_query_data):
        assert self._query(graphql_client_query_data, 'en') == {
            'pledgeTermsUrl': None,
            'pledgePrivacyUrl': None,
            'pledgeAccountTitle': None,
            'pledgeAccountDescription': None,
            'pledgeMarketingConsentLabel': None,
        }

    def test_texts_come_back_in_the_request_language(self, graphql_client_query_data):
        self.plan.pledge_marketing_consent_label = 'Send me news'
        self.plan.pledge_marketing_consent_label_fi = 'Lähettäkää minulle uutisia'  # type: ignore[attr-defined]
        self.plan.save()

        en = self._query(graphql_client_query_data, 'en')
        fi = self._query(graphql_client_query_data, 'fi')

        assert en['pledgeMarketingConsentLabel'] == 'Send me news'
        assert fi['pledgeMarketingConsentLabel'] == 'Lähettäkää minulle uutisia'

    def test_links_are_the_same_in_every_language(self, graphql_client_query_data):
        self.plan.pledge_terms_url = 'https://example.com/terms'
        self.plan.pledge_privacy_url = 'https://example.com/privacy'
        self.plan.save()

        for lang in ('en', 'fi'):
            result = self._query(graphql_client_query_data, lang)
            assert result['pledgeTermsUrl'] == 'https://example.com/terms'
            assert result['pledgePrivacyUrl'] == 'https://example.com/privacy'

    def test_untranslated_texts_fall_back_to_the_primary_language(self, graphql_client_query_data):
        self.plan.pledge_account_title = 'Join us'
        self.plan.pledge_account_description = 'Keep track of your pledges.'
        self.plan.save()

        fi = self._query(graphql_client_query_data, 'fi')

        assert fi['pledgeAccountTitle'] == 'Join us'
        assert fi['pledgeAccountDescription'] == 'Keep track of your pledges.'


class TestAccountsRequireTermsLink:
    def test_offering_accounts_without_a_terms_link_is_refused(self):
        plan = _create_engagement_plan()
        plan.features.enable_community_engagement_accounts = True

        with pytest.raises(ValidationError) as exc_info:
            plan.features.full_clean()

        assert 'enable_community_engagement_accounts' in exc_info.value.message_dict

    def test_offering_accounts_with_a_terms_link_is_allowed(self):
        plan = _create_engagement_plan()
        plan.pledge_terms_url = 'https://example.com/terms'
        plan.save()
        plan.features.enable_community_engagement_accounts = True

        plan.features.full_clean()


class TestPledgeAccountSettingsAdmin:
    def test_settings_are_editable_by_plan_admins_on_the_community_engagement_tab(self, plan, plan_admin_user, client):
        ClientPlanFactory.create(plan=plan)
        plan.features.enable_community_engagement = True
        plan.features.save()
        client.force_login(plan_admin_user)

        response = client.get(reverse(PlanViewSet().get_url_name('edit'), args=[plan.pk]))

        assert response.status_code == 200
        body = response.content.decode('utf-8')
        assert 'Pledge accounts' in body
        assert 'name="pledge_terms_url"' in body
        assert 'name="pledge_marketing_consent_label"' in body

    def test_links_have_one_input_and_texts_one_per_language(self, plan, plan_admin_user, client):
        ClientPlanFactory.create(plan=plan)
        plan.other_languages = ['fi']
        plan.save()
        plan.features.enable_community_engagement = True
        plan.features.save()
        client.force_login(plan_admin_user)

        response = client.get(reverse(PlanViewSet().get_url_name('edit'), args=[plan.pk]))

        body = response.content.decode('utf-8')
        assert 'name="pledge_marketing_consent_label_fi"' in body
        assert 'name="pledge_terms_url_fi"' not in body
        assert 'name="pledge_privacy_url_fi"' not in body


def test_copying_a_plan_keeps_its_pledge_account_settings(plan_with_pages):
    plan_with_pages.pledge_terms_url = 'https://example.com/terms'
    plan_with_pages.pledge_marketing_consent_label = 'Send me news'
    plan_with_pages.save()

    plan_copy = copy_plan(plan_with_pages)

    assert plan_copy.pledge_terms_url == 'https://example.com/terms'
    assert plan_copy.pledge_marketing_consent_label == 'Send me news'
