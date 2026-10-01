from __future__ import annotations

from django.core.exceptions import ValidationError
from django.urls import reverse

import pytest

from actions.models import PledgeCommitment, PublicUser
from actions.models.pledge import PLEDGE_FORM_FIELD_VALUE_MAX_LENGTH
from actions.tests.factories import PlanFactory, PledgeFactory, PledgeFormFieldFactory
from actions.wagtail_admin import PlanViewSet
from admin_site.tests.factories import ClientFactory, ClientPlanFactory
from copying.main import copy_plan

pytestmark = pytest.mark.django_db


PLEDGE_FORM_FIELDS_QUERY = """
    query($plan: ID!, $lang: String!) @locale(lang: $lang) {
        plan(id: $plan) {
            pledgeFormFields {
                identifier
                label
                helpText
                placeholder
                required
            }
        }
    }
"""

SET_USER_DATA_MUTATION = """
    mutation($userUuid: UUID!, $key: String!, $value: String!) {
      pledge {
        setUserData(userUuid: $userUuid, key: $key, value: $value) {
          uuid
        }
      }
    }
"""


def _create_engagement_plan(**kwargs):
    plan = PlanFactory.create(primary_client=ClientFactory.create(), **kwargs)
    plan.features.enable_community_engagement = True
    plan.features.save()
    return plan


class TestPledgeFormFieldsQuery:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = _create_engagement_plan(primary_language='en', other_languages=['fi'])

    def test_returns_fields_in_order(self, graphql_client_query_data):
        PledgeFormFieldFactory.create(plan=self.plan, identifier='district', label='District')
        PledgeFormFieldFactory.create(
            plan=self.plan,
            identifier='postal_code',
            label='Postal code',
            help_text='Where you live',
            placeholder='00100',
            required=True,
        )

        data = graphql_client_query_data(PLEDGE_FORM_FIELDS_QUERY, variables={'plan': self.plan.identifier, 'lang': 'en'})

        assert data['plan']['pledgeFormFields'] == [
            {'identifier': 'district', 'label': 'District', 'helpText': '', 'placeholder': '', 'required': False},
            {
                'identifier': 'postal_code',
                'label': 'Postal code',
                'helpText': 'Where you live',
                'placeholder': '00100',
                'required': True,
            },
        ]

    def test_returns_translated_labels(self, graphql_client_query_data):
        field = PledgeFormFieldFactory.create(plan=self.plan, identifier='postal_code', label='Postal code')
        field.label_fi = 'Postinumero'  # type: ignore[attr-defined]
        field.save()

        data_fi = graphql_client_query_data(PLEDGE_FORM_FIELDS_QUERY, variables={'plan': self.plan.identifier, 'lang': 'fi'})
        data_en = graphql_client_query_data(PLEDGE_FORM_FIELDS_QUERY, variables={'plan': self.plan.identifier, 'lang': 'en'})

        assert data_fi['plan']['pledgeFormFields'][0]['label'] == 'Postinumero'
        assert data_en['plan']['pledgeFormFields'][0]['label'] == 'Postal code'

    def test_falls_back_to_primary_language(self, graphql_client_query_data):
        PledgeFormFieldFactory.create(plan=self.plan, identifier='postal_code', label='Postal code')

        data = graphql_client_query_data(PLEDGE_FORM_FIELDS_QUERY, variables={'plan': self.plan.identifier, 'lang': 'fi'})

        assert data['plan']['pledgeFormFields'][0]['label'] == 'Postal code'

    def test_empty_when_feature_disabled(self, graphql_client_query_data):
        PledgeFormFieldFactory.create(plan=self.plan, identifier='postal_code')
        self.plan.features.enable_community_engagement = False
        self.plan.features.save()

        data = graphql_client_query_data(PLEDGE_FORM_FIELDS_QUERY, variables={'plan': self.plan.identifier, 'lang': 'en'})

        assert data['plan']['pledgeFormFields'] == []


class TestSetUserDataValidation:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.plan = _create_engagement_plan()
        PledgeFormFieldFactory.create(plan=self.plan, identifier='postal_code')
        self.public_user = PublicUser.objects.create(client=self.plan.primary_client)

    def _set(self, graphql_client_query, key: str, value: str):
        return graphql_client_query(
            SET_USER_DATA_MUTATION,
            variables={'userUuid': str(self.public_user.uuid), 'key': key, 'value': value},
        )

    def test_configured_key_is_saved(self, graphql_client_query):
        response = self._set(graphql_client_query, 'postal_code', '00100')

        assert 'errors' not in response
        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {'postal_code': '00100'}

    def test_empty_value_clears(self, graphql_client_query):
        self.public_user.user_data = {'postal_code': '00100'}
        self.public_user.save()

        response = self._set(graphql_client_query, 'postal_code', '')

        assert 'errors' not in response
        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {'postal_code': ''}

    def test_unknown_key_is_rejected(self, graphql_client_query):
        response = self._set(graphql_client_query, 'zip_code', '95616')

        assert response['errors'][0]['extensions']['code'] == 'UNKNOWN_FIELD'
        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {}

    def test_key_configured_on_another_plan_is_rejected(self, graphql_client_query):
        other_plan = _create_engagement_plan()
        PledgeFormFieldFactory.create(plan=other_plan, identifier='zip_code')

        response = self._set(graphql_client_query, 'zip_code', '95616')

        assert response['errors'][0]['extensions']['code'] == 'UNKNOWN_FIELD'

    def test_value_at_max_length_is_saved(self, graphql_client_query):
        value = 'x' * PLEDGE_FORM_FIELD_VALUE_MAX_LENGTH

        response = self._set(graphql_client_query, 'postal_code', value)

        assert 'errors' not in response

    def test_value_over_max_length_is_rejected(self, graphql_client_query):
        response = self._set(graphql_client_query, 'postal_code', 'x' * (PLEDGE_FORM_FIELD_VALUE_MAX_LENGTH + 1))

        assert response['errors'][0]['extensions']['code'] == 'VALUE_TOO_LONG'
        self.public_user.refresh_from_db()
        assert self.public_user.user_data == {}

    def test_rejected_when_feature_disabled(self, graphql_client_query):
        self.plan.features.enable_community_engagement = False
        self.plan.features.save()

        response = self._set(graphql_client_query, 'postal_code', '00100')

        assert response['errors'][0]['extensions']['code'] == 'COMMUNITY_ENGAGEMENT_DISABLED'


class TestPledgeFormFieldModel:
    def test_identifier_cannot_be_changed_after_saving(self):
        field = PledgeFormFieldFactory.create(identifier='postal_code')
        field.identifier = 'zip_code'

        with pytest.raises(ValidationError) as exc_info:
            field.full_clean()

        assert 'identifier' in exc_info.value.message_dict

    def test_other_attributes_can_be_changed(self):
        field = PledgeFormFieldFactory.create(identifier='postal_code', label='Postal code')
        field.label = 'Your postal code'

        field.full_clean()

    def test_new_field_can_set_identifier(self):
        plan = PlanFactory.create()
        field = PledgeFormFieldFactory.build(plan=plan, identifier='postal_code')

        field.full_clean()

    def test_copying_plan_copies_fields(self, plan_with_pages):
        PledgeFormFieldFactory.create(plan=plan_with_pages, identifier='postal_code', label='Postal code')
        PledgeFormFieldFactory.create(plan=plan_with_pages, identifier='district', label='District')

        plan_copy = copy_plan(plan_with_pages)

        copied = list(plan_copy.pledge_form_fields.values_list('identifier', 'label'))
        assert copied == [('postal_code', 'Postal code'), ('district', 'District')]
        assert plan_with_pages.pledge_form_fields.count() == 2


class TestPlanEditCommunityEngagementTab:
    def _edit_url(self, plan) -> str:
        return reverse(PlanViewSet().get_url_name('edit'), args=[plan.pk])

    def test_tab_shown_to_plan_admin_when_feature_enabled(self, plan, plan_admin_user, client):
        ClientPlanFactory.create(plan=plan)
        plan.features.enable_community_engagement = True
        plan.features.save()
        client.force_login(plan_admin_user)

        response = client.get(self._edit_url(plan))

        assert response.status_code == 200
        assert 'Collected data fields' in response.content.decode('utf-8')

    def test_tab_hidden_when_feature_disabled(self, plan, plan_admin_user, client):
        ClientPlanFactory.create(plan=plan)
        client.force_login(plan_admin_user)

        response = client.get(self._edit_url(plan))

        assert response.status_code == 200
        assert 'Collected data fields' not in response.content.decode('utf-8')


class TestParticipantsColumnsUseConfiguredFields:
    @pytest.fixture
    def active_plan(self, plan_admin_user):
        plan = plan_admin_user.get_active_admin_plan()
        plan.features.enable_community_engagement = True
        plan.features.save()
        return plan

    def _participant(self, email: str, user_data: dict[str, str]) -> PublicUser:
        from django.utils import timezone

        now = timezone.now()
        return PublicUser.objects.create(
            email=email,
            client=ClientFactory.create(),
            terms_accepted_at=now,
            marketing_consented_at=now,
            email_verified_at=now,
            user_data=user_data,
        )

    def test_csv_uses_configured_order_and_labels_then_other_keys(self, client, plan_admin_user, active_plan):
        PledgeFormFieldFactory.create(plan=active_plan, identifier='postal_code', label='Postal code')
        PledgeFormFieldFactory.create(plan=active_plan, identifier='district', label='District')
        pledge = PledgeFactory.create(plan=active_plan)
        alice = self._participant('alice@example.com', {'district': 'Kallio', 'zip_code': '95616'})
        PledgeCommitment.objects.create(pledge=pledge, public_user=alice)
        client.force_login(plan_admin_user)

        response = client.get(reverse('pledge_participants_export_csv'))

        assert response.status_code == 200
        lines = response.content.decode('utf-8').splitlines()
        assert lines[0] == 'Email,Postal code,District,Zip code'
        assert lines[1] == 'alice@example.com,,Kallio,95616'
