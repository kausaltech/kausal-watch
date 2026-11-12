from __future__ import annotations

from django.urls import reverse

import pytest

from admin_site.tests.factories import ClientPlanFactory
from orgs.tests.factories import OrganizationFactory

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize('url_name', ['add', 'add_child'])
def test_organization_create_form_does_not_autosave(client, plan_with_pages, plan_admin_user, url_name):
    """
    The create form must not save in the background.

    A background save posts to the create URL, and so does the save button until that save has
    been answered. With both in flight the organization is created twice.
    """
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    kwargs = {}
    if url_name == 'add_child':
        parent = OrganizationFactory.create()
        plan_with_pages.related_organizations.add(parent)
        kwargs['parent_pk'] = parent.pk

    response = client.get(reverse(f'wagtailsnippets_orgs_organization:{url_name}', kwargs=kwargs))

    assert response.status_code == 200
    assert response.context['autosave_enabled'] is False
    assert 'data-w-autosave-interval-value' not in response.content.decode()
