import pytest

from admin_site.chooser import ClientForm
from admin_site.tests.factories import EmailDomainsFactory

pytestmark = pytest.mark.django_db


def _form_data(name='New Client', hostname='example.com'):
    return {
        'name': name,
        'auth_backend': 'azure_ad',
        'default_email_hostname': hostname,
    }


def test_client_form_rejects_duplicate_email_domain():
    EmailDomainsFactory.create(domain='taken.example')
    form = ClientForm(data=_form_data(hostname='taken.example'))
    assert not form.is_valid()
    assert 'default_email_hostname' in form.errors
    assert 'taken.example' in str(form.errors['default_email_hostname'])


def test_client_form_accepts_unused_email_domain():
    form = ClientForm(data=_form_data(hostname='fresh.example'))
    assert form.is_valid(), form.errors
