"""The person admin views."""

from __future__ import annotations

import html
import re

from django.core import mail
from django.urls import reverse

import pytest

from actions.models import ActionContactPerson, PlanPublicSiteViewer
from actions.tests.factories import ActionContactFactory, ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from admin_site.tests.utils import post_data
from audit_logging.models import PlanScopedModelLogEntry
from orgs.models import OrganizationPlanAdmin
from orgs.tests.factories import OrganizationFactory
from people.models import Person
from people.tests.factories import PersonFactory

pytestmark = pytest.mark.django_db

PEOPLE_PATH = '/admin/people/person/'


@pytest.fixture(autouse=True)
def plain_static_storage(settings):
    # The listing renders static files that a manifest built for tests may lack
    settings.STORAGES = {**settings.STORAGES, 'staticfiles': {'BACKEND': 'django.contrib.staticfiles.storage.StaticFilesStorage'}}


@pytest.fixture
def admin_client(client, plan_with_pages, plan_admin_user):
    ClientPlanFactory.create(plan=plan_with_pages)
    client.force_login(plan_admin_user)
    return client


@pytest.fixture
def superuser_client(client, plan_with_pages, superuser):
    ClientPlanFactory.create(plan=plan_with_pages)
    superuser.selected_admin_plan = plan_with_pages
    superuser.save(update_fields=['selected_admin_plan'])
    client.force_login(superuser)
    return client


def _person(plan, **kwargs) -> Person:
    kwargs.setdefault('organization', plan.organization)
    return PersonFactory.create(**kwargs)


def _contact_person(plan, role=ActionContactPerson.Role.MODERATOR) -> Person:
    return ActionContactFactory.create(action=ActionFactory.create(plan=plan), role=role).person


def _edit_path(person: Person) -> str:
    return f'{PEOPLE_PATH}edit/{person.pk}/'


def _add_path(response_content: bytes) -> str | None:
    match = re.search(rf'href="({PEOPLE_PATH}(?:create|add)/[^"]*)"', response_content.decode())
    return html.unescape(match.group(1)) if match else None


def _listing(client, query: str = '') -> str:
    return html.unescape(client.get(f'{PEOPLE_PATH}{query}').content.decode())


def _row(content: str, person: Person) -> str:
    """Return the listing row of `person`."""
    rows = re.findall(r'<tr[^>]*>.*?</tr>', content, re.DOTALL)
    matching = [row for row in rows if person.email in row]
    assert len(matching) == 1, person.email
    return matching[0]


def test_menu_links_people(admin_client):
    assert f'"{PEOPLE_PATH}"' in admin_client.get('/admin/account/').content.decode()


def test_listing_shows_people_of_the_active_plan(admin_client, plan_with_pages):
    own = _person(plan_with_pages)
    other = _person(PlanFactory.create())
    content = _listing(admin_client)
    assert own.email in content
    assert other.email not in content


def test_listing_columns(admin_client, plan_with_pages):
    person = _person(plan_with_pages, first_name='Ada', last_name='Lovelace', title='Engineer')
    row = _row(_listing(admin_client), person)
    for text in ('Ada', 'Lovelace', 'Engineer', plan_with_pages.organization.name):
        assert text in row, text
    assert f'href="{_edit_path(person)}"' in row


def test_role_badges(admin_client, plan_with_pages, plan_admin_person):
    contact = _contact_person(plan_with_pages)
    content = _listing(admin_client)
    assert 'person-role--plan_admin' in _row(content, plan_admin_person)
    assert 'person-role--contact_person' in _row(content, contact)


@pytest.mark.parametrize(('role', 'listed'), [('plan_admin', 'admin'), ('contact_person', 'contact'), ('none', 'nobody')])
def test_listing_can_be_filtered_by_role(admin_client, plan_with_pages, plan_admin_person, role, listed):
    people = {'admin': plan_admin_person, 'contact': _contact_person(plan_with_pages), 'nobody': _person(plan_with_pages)}
    content = _listing(admin_client, f'?role={role}')
    for key, person in people.items():
        assert (person.email in content) is (key == listed), key


def test_contact_columns_are_shown_when_filtering_by_contact_person(admin_client, plan_with_pages):
    _contact_person(plan_with_pages)
    assert 'contact for actions' not in _listing(admin_client).lower()
    assert 'contact for actions' in _listing(admin_client, '?role=contact_person').lower()


def test_last_login_and_training_columns_are_for_plan_admins(client, admin_client, plan_with_pages):
    assert 'last login' in _listing(admin_client).lower()
    assert 'attended training' in _listing(admin_client).lower()
    contact = _contact_person(plan_with_pages)
    assert contact.user is not None
    client.force_login(contact.user)
    content = _listing(client).lower()
    assert 'last login' not in content
    assert 'attended training' not in content


def test_listing_can_be_searched_by_organization(admin_client, plan_with_pages):
    organization = OrganizationFactory.create(name='Parks department', parent=plan_with_pages.organization)
    match = _person(plan_with_pages, organization=organization)
    other = _person(plan_with_pages)
    content = _listing(admin_client, '?q=Parks')
    assert match.email in content
    assert other.email not in content


def test_people_without_admin_access_are_highlighted(admin_client, plan_with_pages):
    without_access = _person(plan_with_pages)
    contact = _contact_person(plan_with_pages)
    content = _listing(admin_client)
    assert 'warning-row' in _row(content, without_access)
    assert 'warning-row' not in _row(content, contact)


def test_viewers_are_not_highlighted_with_access_requests(admin_client, plan_with_pages):
    plan_with_pages.features.enable_access_requests = True
    plan_with_pages.features.save()
    viewer = _person(plan_with_pages)
    PlanPublicSiteViewer.objects.create(plan=plan_with_pages, person=viewer)
    assert 'warning-row' not in _row(_listing(admin_client), viewer)


def test_row_actions(admin_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    row = _row(_listing(admin_client), contact)
    assert 'Edit' in row
    assert f'{PEOPLE_PATH}delete/{contact.pk}/' in row
    assert 'Deactivate' in row


def test_reset_password_is_offered_for_people_with_a_password(admin_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    assert contact.user is not None
    reset_path = f'{PEOPLE_PATH}reset_password/{contact.pk}/'
    contact.user.set_unusable_password()
    contact.user.save()
    assert reset_path not in _row(_listing(admin_client), contact)
    contact.user.set_password('secret-password')
    contact.user.save()
    assert reset_path in _row(_listing(admin_client), contact)


def test_view_as_user_is_for_superusers(superuser_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    assert f'{PEOPLE_PATH}view_as_user/{contact.pk}/' in _row(_listing(superuser_client), contact)


def test_plan_admin_cannot_view_as_user(admin_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    assert 'view_as_user' not in _row(_listing(admin_client), contact)


def _post_data(form) -> dict:
    data = post_data(form)
    data.pop('image', None)  # An empty file field can't be posted back
    return data


def _creation_data(client, plan) -> tuple[str, dict]:
    add_path = _add_path(client.get(PEOPLE_PATH).content)
    assert add_path is not None
    data = _post_data(client.get(add_path).context['form'])
    data.update({
        'first_name': 'Grace',
        'last_name': 'Hopper',
        'email': 'grace@example.com',
        'organization': plan.organization.pk,
    })
    return add_path, data


def test_plan_admin_creates_a_plan_admin(admin_client, plan_with_pages):
    add_path, data = _creation_data(admin_client, plan_with_pages)
    data['is_admin_for_active_plan'] = 'on'
    response = admin_client.post(add_path, data)
    assert response.status_code == 302
    assert response['Location'] == PEOPLE_PATH
    person = Person.objects.get(email='grace@example.com')
    assert plan_with_pages in person.general_admin_plans.all()


def test_creating_a_public_site_viewer(admin_client, plan_with_pages):
    add_path, data = _creation_data(admin_client, plan_with_pages)
    data['access_level'] = 'public_site_only'
    assert admin_client.post(add_path, data).status_code == 302
    person = Person.objects.get(email='grace@example.com')
    assert PlanPublicSiteViewer.objects.filter(plan=plan_with_pages, person=person).exists()


def test_public_site_viewer_cannot_be_a_plan_admin(admin_client, plan_with_pages):
    add_path, data = _creation_data(admin_client, plan_with_pages)
    data.update({'access_level': 'public_site_only', 'is_admin_for_active_plan': 'on'})
    response = admin_client.post(add_path, data)
    assert response.status_code == 200
    assert not Person.objects.filter(email='grace@example.com').exists()


def test_editing_saves_organization_plan_admins(admin_client, plan_with_pages):
    person = _contact_person(plan_with_pages)
    path = _edit_path(person)
    form = admin_client.get(path).context['form']
    assert {'access_level', 'is_admin_for_active_plan', 'participated_in_training'} <= set(form.fields)
    data = _post_data(form)
    data['organization_plan_admin_orgs'] = [plan_with_pages.organization.pk]
    response = admin_client.post(path, data)
    assert response.status_code == 302
    assert response['Location'] == PEOPLE_PATH
    assert OrganizationPlanAdmin.objects.filter(plan=plan_with_pages, person=person).exists()


def test_contact_person_edits_themselves_with_the_basic_form(client, plan_with_pages):
    ClientPlanFactory.create(plan=plan_with_pages)
    contact = _contact_person(plan_with_pages)
    assert contact.user is not None
    client.force_login(contact.user)
    response = client.get(_edit_path(contact))
    assert response.status_code == 200
    assert 'access_level' not in response.context['form'].fields
    assert client.get(_edit_path(_person(plan_with_pages))).status_code == 302


@pytest.mark.parametrize(
    ('role', 'can_create'), [(ActionContactPerson.Role.MODERATOR, True), (ActionContactPerson.Role.EDITOR, False)]
)
def test_contact_person_creates_people_unless_an_editor(client, plan_with_pages, role, can_create):
    ClientPlanFactory.create(plan=plan_with_pages)
    contact = _contact_person(plan_with_pages, role=role)
    assert contact.user is not None
    client.force_login(contact.user)
    assert (_add_path(client.get(PEOPLE_PATH).content) is not None) is can_create


def test_deactivate_page_lists_linked_objects(admin_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    content = admin_client.get(f'{PEOPLE_PATH}delete/{contact.pk}/').content.decode()
    assert 'Are you sure you want to deactivate this person?' in content
    assert str(contact.contact_for_actions.get()) in content


def test_deactivating_deletes_the_person_and_deactivates_the_user(admin_client, plan_with_pages):
    person = _person(plan_with_pages)
    user = person.user
    assert user is not None
    response = admin_client.post(f'{PEOPLE_PATH}delete/{person.pk}/')
    assert response.status_code == 302
    assert response['Location'] == PEOPLE_PATH
    assert not Person.objects.filter(pk=person.pk).exists()
    user.refresh_from_db()
    assert not user.is_active


def test_deactivating_logs_the_deletion(admin_client, plan_with_pages):
    person = _person(plan_with_pages)
    admin_client.post(f'{PEOPLE_PATH}delete/{person.pk}/')
    assert PlanScopedModelLogEntry.objects.filter(action='wagtail.delete', object_id=str(person.pk)).exists()


def test_other_plan_person_cannot_be_deactivated(admin_client):
    person = _person(PlanFactory.create())
    admin_client.post(f'{PEOPLE_PATH}delete/{person.pk}/')
    assert Person.objects.filter(pk=person.pk).exists()


def test_other_plan_person_cannot_be_edited(admin_client):
    person = _person(PlanFactory.create(), first_name='Ada')
    response = admin_client.get(_edit_path(person))
    assert response.status_code == 302
    assert 'Ada' not in response.content.decode()
    admin_client.post(_edit_path(person), {'first_name': 'Changed'})
    person.refresh_from_db()
    assert person.first_name == 'Ada'


def test_resetting_a_password(admin_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    path = f'{PEOPLE_PATH}reset_password/{contact.pk}/'
    assert 'Do you really want to send a password reset link' in admin_client.get(path).content.decode()
    response = admin_client.post(path, follow=True)
    assert response.redirect_chain[0][0] == PEOPLE_PATH
    assert [message.to for message in mail.outbox] == [[contact.email]]
    assert any('/admin/password_reset/confirm/' in str(m) for m in response.context['messages'])


def test_password_of_a_plan_admin_cannot_be_reset(admin_client, plan_with_pages):
    other_admin = _person(plan_with_pages)
    other_admin.general_admin_plans.add(plan_with_pages)
    response = admin_client.post(f'{PEOPLE_PATH}reset_password/{other_admin.pk}/')
    assert response.status_code == 302
    assert response['Location'] == '/admin/'
    assert mail.outbox == []


def test_contact_person_cannot_reset_passwords(client, plan_with_pages):
    ClientPlanFactory.create(plan=plan_with_pages)
    contact = _contact_person(plan_with_pages)
    assert contact.user is not None
    client.force_login(contact.user)
    client.post(f'{PEOPLE_PATH}reset_password/{_contact_person(plan_with_pages).pk}/')
    assert mail.outbox == []


def test_view_as_user_confirmation(superuser_client, plan_with_pages):
    contact = _contact_person(plan_with_pages)
    response = superuser_client.get(f'{PEOPLE_PATH}view_as_user/{contact.pk}/')
    assert response.status_code == 200
    content = response.content.decode()
    assert 'Do you really want to view the site as' in content
    assert f'action="{reverse("hijack:acquire")}"' in content


def test_plan_admin_cannot_open_view_as_user(admin_client, plan_with_pages):
    response = admin_client.get(f'{PEOPLE_PATH}view_as_user/{_contact_person(plan_with_pages).pk}/')
    assert response.status_code == 302
    assert response['Location'] == '/admin/'
