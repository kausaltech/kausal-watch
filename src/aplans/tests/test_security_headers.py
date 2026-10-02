from __future__ import annotations

from django.urls import reverse

import pytest


@pytest.fixture
def liveness_url():
    return reverse('liveness')


@pytest.mark.django_db
def test_hsts_header_set_on_secure_request(client, liveness_url):
    response = client.get(liveness_url, secure=True)

    assert response.headers['Strict-Transport-Security'] == 'max-age=300; includeSubDomains'


@pytest.mark.django_db
def test_hsts_header_not_set_on_insecure_request(client, liveness_url):
    response = client.get(liveness_url)

    assert 'Strict-Transport-Security' not in response.headers
