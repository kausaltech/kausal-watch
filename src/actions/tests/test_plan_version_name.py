from __future__ import annotations

from django.urls import reverse
from wagtail.users.models import UserProfile

import pytest

from actions.models import Plan
from actions.tests.factories import PlanFactory

pytestmark = pytest.mark.django_db


VERSION_NAME_QUERY = """
    query($plan: ID!, $lang: String!) @locale(lang: $lang) {
        plan(id: $plan) {
            versionName
        }
    }
"""


@pytest.mark.parametrize(
    ('lang', 'i18n', 'expected'),
    [
        ('en', {'version_name_fi': 'Luonnos'}, 'Draft'),
        ('fi', {'version_name_fi': 'Luonnos'}, 'Luonnos'),
        # Without a translation, the version name falls back to the primary language.
        ('fi', {}, 'Draft'),
    ],
)
def test_version_name_is_translated(graphql_client_query_data, lang, i18n, expected):
    plan = PlanFactory.create(primary_language='en', other_languages=['fi'], version_name='Draft', i18n=i18n)
    data = graphql_client_query_data(VERSION_NAME_QUERY, variables={'plan': plan.identifier, 'lang': lang})
    assert data['plan']['versionName'] == expected


@pytest.mark.parametrize('primary_version_name', ['Draft', ''])
def test_admin_header_shows_the_translated_version_name(client, plan, plan_admin_user, primary_version_name):
    """The header shows the version name in the admin language, even if the primary language has none."""
    assert plan.primary_language == 'en'
    assert plan.other_languages == ['fi']
    Plan.objects.filter(pk=plan.pk).update(version_name=primary_version_name, i18n={'version_name_fi': 'Luonnos'})
    profile = UserProfile.get_for_user(plan_admin_user)
    profile.preferred_language = 'fi'
    profile.save()
    client.force_login(plan_admin_user)
    response = client.get(reverse('wagtailadmin_home'))
    assert response.status_code == 200
    assert '<span class="active-plan-version-name">Luonnos</span>' in response.content.decode()
