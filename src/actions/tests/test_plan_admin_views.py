from __future__ import annotations

import html
import re

from django.test import Client
from django.urls import reverse
from reversion.models import Version
from wagtail.admin.admin_url_finder import AdminURLFinder

import pytest

from actions.models import Plan
from actions.tests.factories import CategoryTypeFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data, submenu_links
from audit_logging.models import PlanScopedModelLogEntry
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    # The listing renders static files that a manifest built for tests may lack
    settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


@pytest.fixture
def plan_with_client(plan_with_pages):
    ClientPlanFactory.create(plan=plan_with_pages)
    category_type = CategoryTypeFactory.create(plan=plan_with_pages)
    Plan.objects.filter(pk=plan_with_pages.pk).update(primary_action_classification=category_type)
    plan_with_pages.refresh_from_db()
    return plan_with_pages


@pytest.fixture
def admin_client(plan_with_client, plan_admin_user):
    client = Client()
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def superuser_client(plan_with_client, superuser):
    superuser.selected_admin_plan = plan_with_client
    superuser.save(update_fields=['selected_admin_plan'])
    client = Client()
    client.force_login(superuser)
    return client


def _listing_url() -> str:
    return reverse('wagtailsnippets_actions_plan:list')


def _listing(client) -> str:
    return html.unescape(client.get(_listing_url()).content.decode())


def _links(content: str) -> set[str]:
    return set(re.findall(r'href="(/admin/[^"?]+)', content))


def _edit_url(user, plan: Plan) -> str:
    url = AdminURLFinder(user).get_edit_url(plan)
    assert url is not None
    return url


def _link_ending(content: str, suffix: str) -> str:
    matches = [link for link in _links(content) if link.endswith(suffix)]
    assert len(matches) == 1, (suffix, matches)
    return matches[0]


def test_settings_menu_links_to_the_active_plan(admin_client, plan_with_pages, plan_admin_user):
    response = admin_client.get('/admin/')
    links = dict(submenu_links(response.content, 'Settings'))
    assert links['Plan'] == _edit_url(plan_admin_user, plan_with_pages)


def test_plan_admin_lists_own_plans(admin_client, plan_with_pages):
    other = PlanFactory.create(name='Other plan')
    content = _listing(admin_client)
    assert plan_with_pages.name in content
    assert other.name not in content


def test_superuser_lists_all_plans(superuser_client):
    other = PlanFactory.create(name='Other plan')
    assert other.name in _listing(superuser_client)


def test_only_superusers_are_offered_creating_and_copying(superuser_client, admin_client, plan_with_pages):
    plan_admin_listing = _listing(admin_client)
    superuser_listing = _listing(superuser_client)
    copy_suffix = f'/copy/{plan_with_pages.pk}/'
    assert not any(link.endswith(('/create/', '/add/')) for link in _links(plan_admin_listing))
    assert not any(link.endswith(copy_suffix) for link in _links(plan_admin_listing))
    assert any(link.endswith(('/create/', '/add/')) for link in _links(superuser_listing))
    assert superuser_client.get(_link_ending(superuser_listing, copy_suffix)).status_code == 200


def test_plan_admin_cannot_open_creating_or_copying(admin_client, superuser_client, plan_with_pages):
    superuser_listing = _listing(superuser_client)
    add_url = next(link for link in _links(superuser_listing) if link.endswith(('/create/', '/add/')))
    copy_url = _link_ending(superuser_listing, f'/copy/{plan_with_pages.pk}/')
    assert admin_client.get(add_url).status_code != 200
    assert admin_client.get(copy_url).status_code != 200


def test_superuser_is_offered_deleting(superuser_client, plan_with_pages):
    content = _listing(superuser_client)
    assert any(link.endswith(f'/delete/{plan_with_pages.pk}/') for link in _links(content))
    assert '/admin/bulk/actions/plan/delete/' in _links(content)


def test_superuser_deletes_a_plan(superuser_client):
    plan = PlanFactory.create(name='Doomed plan')
    delete_url = _link_ending(_listing(superuser_client), f'/delete/{plan.pk}/')
    assert superuser_client.get(delete_url).status_code == 200
    superuser_client.post(delete_url)
    assert not Plan.objects.filter(pk=plan.pk).exists()


def test_superuser_bulk_deletes_plans(superuser_client):
    plans = [PlanFactory.create(), PlanFactory.create()]
    query = '&'.join(f'id={plan.pk}' for plan in plans)
    superuser_client.post(f'/admin/bulk/actions/plan/delete/?{query}')
    assert not Plan.objects.filter(pk__in=[plan.pk for plan in plans]).exists()


def test_plan_admin_is_not_offered_deleting(admin_client, plan_with_pages):
    content = _listing(admin_client)
    assert not any(link.endswith(f'/delete/{plan_with_pages.pk}/') for link in _links(content))


def test_plan_admin_cannot_delete(admin_client, superuser_client, plan_with_pages):
    delete_url = _link_ending(_listing(superuser_client), f'/delete/{plan_with_pages.pk}/')
    admin_client.post(delete_url)
    admin_client.post(f'/admin/bulk/actions/plan/delete/?id={plan_with_pages.pk}')
    assert Plan.objects.filter(pk=plan_with_pages.pk).exists()


def test_plan_admin_edits_own_plan(admin_client, plan_with_pages, plan_admin_user):
    edit_url = _edit_url(plan_admin_user, plan_with_pages)
    response = admin_client.get(edit_url)
    assert response.status_code == 200
    data = post_data(response.context['form'])
    data['name'] = 'Renamed plan'
    response = admin_client.post(edit_url, data)
    assert response.status_code == 302
    assert response['Location'] == edit_url
    plan_with_pages.refresh_from_db()
    assert plan_with_pages.name == 'Renamed plan'


def test_editing_records_a_revision_and_an_audit_entry(admin_client, plan_with_pages, plan_admin_user):
    edit_url = _edit_url(plan_admin_user, plan_with_pages)
    data = post_data(admin_client.get(edit_url).context['form'])
    admin_client.post(edit_url, data)
    assert Version.objects.get_for_object(plan_with_pages).exists()
    assert PlanScopedModelLogEntry.objects.filter(action='wagtail.edit', object_id=str(plan_with_pages.pk)).exists()


def test_plan_admin_cannot_edit_another_plan(admin_client, superuser, plan_with_pages):
    other = PlanFactory.create(name='Other plan')
    edit_url = _edit_url(superuser, other)
    response = admin_client.get(edit_url)
    assert response.status_code == 302
    assert 'Other plan' not in response.content.decode()


def test_plan_admin_of_two_plans_edits_the_other_plan_without_switching(client, plan_with_client, superuser):
    other = PlanFactory.create()
    ClientPlanFactory.create(plan=other)
    user = PersonFactory.create(general_admin_plans=[plan_with_client, other]).user
    assert user is not None
    client.force_login(user)
    active = user.get_active_admin_plan()
    inactive = other if active == plan_with_client else plan_with_client
    assert client.get(_edit_url(superuser, inactive)).status_code == 200


@pytest.mark.parametrize(('as_superuser', 'shown'), [(True, True), (False, False)])
def test_superuser_only_fields(admin_client, superuser_client, plan_with_pages, plan_admin_user, superuser, as_superuser, shown):
    client, user = (superuser_client, superuser) if as_superuser else (admin_client, plan_admin_user)
    form = client.get(_edit_url(user, plan_with_pages)).context['form']
    for field in ('visibility', 'usage_status', 'theme_identifier'):
        assert (field in form.fields) is shown, field


def test_edit_page_has_the_action_classification_tab(admin_client, plan_with_pages, plan_admin_user):
    content = admin_client.get(_edit_url(plan_admin_user, plan_with_pages)).content.decode()
    assert 'Action classifications' in content


def test_superuser_creates_a_plan(superuser_client, plan_with_client):
    add_url = next(link for link in _links(_listing(superuser_client)) if link.endswith(('/create/', '/add/')))
    form = superuser_client.get(add_url).context['form']
    assert 'organization' in form.fields
    assert 'visibility' not in form.fields
    data = post_data(form)
    data.update(
        name='New plan',
        identifier='new-plan',
        organization_name='New organization',
        primary_language='en',
        country='FI',
        **{'clients-0-client': plan_with_client.clients.get().client.pk, 'clients-0-is_primary': 'on'},
    )
    response = superuser_client.post(add_url, data)
    plan = Plan.objects.get(identifier='new-plan')
    assert response.status_code == 302
    assert response['Location'] == reverse('change-admin-plan', kwargs={'plan_id': plan.pk})
