from __future__ import annotations

from django.core.exceptions import ValidationError

import pytest

from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


def test_organization_save_normalizes_bare_void_tag() -> None:
    # Organization.description is a native Wagtail RichTextField (not modeltrans-managed),
    # so it returns a RichText wrapper on access rather than a plain str.
    org = OrganizationFactory.create(description='<p>a<br>b</p>')
    org.refresh_from_db()
    assert org.description == '<p>a<br/>b</p>'


def test_organization_save_rejects_irreparable_markup() -> None:
    org = OrganizationFactory.create()
    org.description = '<p><em>crossed</p></em>'
    with pytest.raises(ValidationError):
        org.save()
