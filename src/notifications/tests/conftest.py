import pytest


@pytest.fixture(autouse=True)
def _notification_test_settings(settings) -> None:
    settings.ADMIN_BASE_URL = 'https://admin.example.com'
