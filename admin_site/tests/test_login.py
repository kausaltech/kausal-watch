from unittest.mock import Mock
from urllib.parse import parse_qs, urlparse

from django.test import override_settings
from django.urls import reverse

import pytest
from pytest_django.asserts import assertContains

from admin_site.backends import SingleTenantSpecificEntraAuth

pytestmark = pytest.mark.django_db


def test_admin_login_uses_post_form_for_social_auth(client):
    response = client.get(reverse('wagtailadmin_login'))

    assert response.status_code == 200
    assertContains(response, '<form id="social-login-form" method="post" hidden>')
    assertContains(response, '<input type="hidden" name="csrfmiddlewaretoken"', count=2)
    assertContains(response, '<input type="hidden" name="next" />')
    assertContains(response, '<input type="hidden" name="email" />')


@override_settings(SOCIAL_AUTH_AZURE_AD_KEY='client-id', SOCIAL_AUTH_AZURE_AD_SECRET='client-secret')
def test_azure_ad_auth_entry_requires_post_and_forwards_email(client):
    url = reverse('social:begin', args=['azure_ad'])

    assert client.get(url).status_code == 405

    response = client.post(url, {'next': '/admin/', 'email': 'juha.yrjola@kausal.tech'})

    assert response.status_code == 302
    assert response['Location'].startswith('https://login.microsoftonline.com/organizations/oauth2/authorize?')
    query = parse_qs(urlparse(response['Location']).query)
    assert query['login_hint'] == ['juha.yrjola@kausal.tech']
    assert client.session['next'] == '/admin/'


def get_social_auth_strategy(settings_by_name: dict[str, str]) -> Mock:
    def get_setting(name, default=None, **_kwargs):
        return settings_by_name.get(name, default)

    strategy = Mock()
    strategy.request_data.return_value = {}
    strategy.absolute_uri.side_effect = lambda uri: uri
    strategy.setting.side_effect = get_setting
    return strategy


def test_single_tenant_entra_uses_tenant_openid_metadata(settings):
    settings.SINGLE_TENANT_SPECIFIC_ENTRA_TENANT_ID = '847f3667-75cc-4621-9eb2-29c242d15f13'
    backend = SingleTenantSpecificEntraAuth(get_social_auth_strategy({}))

    assert backend.openid_configuration_url() == (
        'https://login.microsoftonline.com/847f3667-75cc-4621-9eb2-29c242d15f13/.well-known/openid-configuration'
    )
