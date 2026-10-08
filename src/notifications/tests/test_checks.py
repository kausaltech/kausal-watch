import pytest

from notifications.checks import check_admin_base_url


def test_check_errors_for_localhost_admin_url(settings):
    settings.DEPLOYMENT_TYPE = 'production'
    settings.ADMIN_BASE_URL = 'http://localhost:8000'
    errors = check_admin_base_url(app_configs=None)
    assert len(errors) == 1
    assert errors[0].id == 'notifications.E001'


def test_check_errors_for_ip_admin_url(settings):
    settings.DEPLOYMENT_TYPE = 'production'
    settings.ADMIN_BASE_URL = 'http://192.168.1.1/admin/'
    errors = check_admin_base_url(app_configs=None)
    assert len(errors) == 1
    assert errors[0].id == 'notifications.E001'


def test_check_errors_for_unsupported_admin_url_scheme(settings):
    settings.DEPLOYMENT_TYPE = 'production'
    settings.ADMIN_BASE_URL = 'ftp://admin.example.com/admin/'
    errors = check_admin_base_url(app_configs=None)
    assert len(errors) == 1
    assert errors[0].id == 'notifications.E001'


def test_check_errors_for_plaintext_http_admin_url(settings):
    settings.DEPLOYMENT_TYPE = 'production'
    settings.ADMIN_BASE_URL = 'http://admin.example.com'
    errors = check_admin_base_url(app_configs=None)
    assert len(errors) == 1
    assert errors[0].id == 'notifications.E001'


def test_check_passes_for_public_admin_url(settings):
    settings.DEPLOYMENT_TYPE = 'production'
    settings.ADMIN_BASE_URL = 'https://admin.example.com'
    assert check_admin_base_url(app_configs=None) == []


@pytest.mark.parametrize('deployment_type', ['development', 'ci'])
def test_check_allows_localhost_in_development_and_ci(settings, deployment_type):
    settings.DEPLOYMENT_TYPE = deployment_type
    settings.ADMIN_BASE_URL = 'http://localhost:8000'
    assert check_admin_base_url(app_configs=None) == []


@pytest.mark.parametrize('deployment_type', ['production', 'staging', 'testing', 'wip'])
def test_check_errors_for_localhost_in_deployed_environments(settings, deployment_type):
    settings.DEPLOYMENT_TYPE = deployment_type
    settings.ADMIN_BASE_URL = 'http://localhost:8000'
    errors = check_admin_base_url(app_configs=None)
    assert [e.id for e in errors] == ['notifications.E001']
