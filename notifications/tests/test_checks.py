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


def test_check_passes_for_public_admin_url(settings):
    settings.DEPLOYMENT_TYPE = 'production'
    settings.ADMIN_BASE_URL = 'https://admin.example.com'
    assert check_admin_base_url(app_configs=None) == []


def test_check_allows_localhost_in_development(settings):
    settings.DEPLOYMENT_TYPE = 'development'
    settings.ADMIN_BASE_URL = 'http://localhost:8000'
    assert check_admin_base_url(app_configs=None) == []
