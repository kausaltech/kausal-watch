from __future__ import annotations

import datetime

from django.urls import reverse
from wagtail.test.utils.form_data import inline_formset, nested_form_data, rich_text

import pytest

from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.tests.factories import ClientPlanFactory
from images.tests.factories import AplansImageFactory
from indicators.models import Indicator
from indicators.tests.factories import IndicatorFactory
from orgs.models import Organization, OrganizationMetadataAdmin
from orgs.tests.factories import OrganizationFactory
from people.models import Person
from people.tests.factories import PersonFactory

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


INCLUDE_URL = 'wagtailsnippets_orgs_organization:include_organization_in_active_plan'
EXCLUDE_URL = 'wagtailsnippets_orgs_organization:exclude_organization_from_active_plan'
DELETE_URL = 'wagtailsnippets_orgs_organization:delete'


def assert_permission_denied(response):
    # Wagtail answers a permission denial in the admin with a redirect to the dashboard.
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')


@pytest.fixture
def two_tenants():
    """Plans A and B with separate root organizations; plan B owns a department with a person and an indicator."""
    plan_a = PlanFactory.create()
    plan_b = PlanFactory.create()
    ClientPlanFactory.create(plan=plan_a)
    dept_b = OrganizationFactory.create(parent=plan_b.organization)
    person_b = PersonFactory.create(organization=dept_b)
    indicator_b = IndicatorFactory.create(organization=dept_b, plans=[plan_b])
    admin_a = PersonFactory.create(general_admin_plans=[plan_a]).user
    assert admin_a is not None
    return plan_a, plan_b, dept_b, person_b, indicator_b, admin_a


def test_plan_admin_cannot_include_other_tenants_department(client, two_tenants):
    plan_a, _plan_b, dept_b, person_b, indicator_b, admin_a = two_tenants
    client.force_login(admin_a)

    response = client.post(reverse(INCLUDE_URL, kwargs={'pk': dept_b.pk}))

    assert_permission_denied(response)
    assert not plan_a.related_organizations.filter(pk=dept_b.pk).exists()
    assert not dept_b.user_can_edit(admin_a)

    response = client.post(reverse(DELETE_URL, kwargs={'pk': dept_b.pk}))

    assert_permission_denied(response)

    assert Organization.objects.filter(pk=dept_b.pk).exists()
    assert Person.objects.filter(pk=person_b.pk).exists()
    assert Indicator.objects.filter(pk=indicator_b.pk).exists()


def test_plan_admin_cannot_include_other_tenants_root(client, two_tenants):
    plan_a, plan_b, _dept_b, _person_b, _indicator_b, admin_a = two_tenants
    client.force_login(admin_a)

    response = client.post(reverse(INCLUDE_URL, kwargs={'pk': plan_b.organization.pk}))

    assert_permission_denied(response)
    assert not plan_a.related_organizations.filter(pk=plan_b.organization.pk).exists()


def test_plan_admin_can_include_and_exclude_own_root(client, two_tenants):
    plan_a, _plan_b, _dept_b, _person_b, _indicator_b, admin_a = two_tenants
    client.force_login(admin_a)
    root_a = plan_a.organization

    client.post(reverse(INCLUDE_URL, kwargs={'pk': root_a.pk}))
    assert plan_a.related_organizations.filter(pk=root_a.pk).exists()

    client.post(reverse(EXCLUDE_URL, kwargs={'pk': root_a.pk}))
    assert not plan_a.related_organizations.filter(pk=root_a.pk).exists()


def test_plan_admin_can_exclude_related_root(client, two_tenants):
    plan_a, _plan_b, _dept_b, _person_b, _indicator_b, admin_a = two_tenants
    shared_root = OrganizationFactory.create()
    plan_a.related_organizations.add(shared_root)
    client.force_login(admin_a)

    client.post(reverse(EXCLUDE_URL, kwargs={'pk': shared_root.pk}))

    assert not plan_a.related_organizations.filter(pk=shared_root.pk).exists()


def test_metadata_admin_can_include_root_they_administer(client, two_tenants):
    plan_a, plan_b, _dept_b, _person_b, _indicator_b, _admin_a = two_tenants
    person = PersonFactory.create(general_admin_plans=[plan_a])
    person.metadata_adminable_organizations.add(plan_b.organization)
    assert person.user is not None
    client.force_login(person.user)

    client.post(reverse(INCLUDE_URL, kwargs={'pk': plan_b.organization.pk}))

    assert plan_a.related_organizations.filter(pk=plan_b.organization.pk).exists()


def test_superuser_can_include_any_root(client, two_tenants):
    plan_a, plan_b, _dept_b, _person_b, _indicator_b, _admin_a = two_tenants
    superuser = PersonFactory.create(general_admin_plans=[plan_a]).user
    assert superuser is not None
    superuser.is_superuser = True
    superuser.selected_admin_plan = plan_a  # a superuser administers every plan; pin the active one
    superuser.save()
    client.force_login(superuser)

    client.post(reverse(INCLUDE_URL, kwargs={'pk': plan_b.organization.pk}))

    assert plan_a.related_organizations.filter(pk=plan_b.organization.pk).exists()


def test_plan_admin_can_exclude_related_non_root(client, two_tenants):
    plan_a, _plan_b, _dept_b, _person_b, _indicator_b, admin_a = two_tenants
    child = OrganizationFactory.create(parent=OrganizationFactory.create())
    plan_a.related_organizations.add(child)
    client.force_login(admin_a)

    client.post(reverse(EXCLUDE_URL, kwargs={'pk': child.pk}))

    assert not plan_a.related_organizations.filter(pk=child.pk).exists()


def test_plan_admin_cannot_include_non_root_available_for_plan(client, two_tenants):
    plan_a, _plan_b, _dept_b, _person_b, _indicator_b, admin_a = two_tenants
    dept_a = OrganizationFactory.create(parent=plan_a.organization)
    client.force_login(admin_a)

    response = client.post(reverse(INCLUDE_URL, kwargs={'pk': dept_a.pk}))

    assert_permission_denied(response)
    assert not plan_a.related_organizations.filter(pk=dept_a.pk).exists()


def test_metadata_admin_without_general_admin_rights_cannot_include(client, two_tenants):
    plan_a, plan_b, _dept_b, _person_b, _indicator_b, _admin_a = two_tenants
    action_a = ActionFactory.create(plan=plan_a)
    person = PersonFactory.create(contact_for_actions=[action_a])
    person.metadata_adminable_organizations.add(plan_b.organization)
    assert person.user is not None
    client.force_login(person.user)

    client.post(reverse(INCLUDE_URL, kwargs={'pk': plan_b.organization.pk}))

    assert not plan_a.related_organizations.filter(pk=plan_b.organization.pk).exists()


def test_contact_person_role_in_other_plan_grants_no_org_edit_rights(two_tenants):
    """Being a general admin of plan A and only an action contact in plan B gives no rights on B's organizations."""
    plan_a, plan_b, dept_b, _person_b, _indicator_b, _admin_a = two_tenants
    action_b = ActionFactory.create(plan=plan_b)
    person = PersonFactory.create(general_admin_plans=[plan_a], contact_for_actions=[action_b])
    user = person.user
    assert user is not None
    assert plan_b in user.get_adminable_plans()

    assert not dept_b.user_can_edit(user)
    assert dept_b not in Organization.objects.qs.editable_by_user(user)
    assert plan_a.organization.user_can_edit(user)
    assert plan_a.organization in Organization.objects.qs.editable_by_user(user)


COPY_URL = 'wagtailsnippets_orgs_organization:copy'


def copy_form_data(name: str, parent: Organization | None) -> dict[str, str]:
    return nested_form_data({
        'name': name,
        'abbreviation': '',
        'internal_abbreviation': '',
        'description': rich_text('<p>Copied</p>'),
        'url': '',
        'email': '',
        'logo': '',
        'parent': str(parent.pk) if parent else '',
        'organization_plan_admins': inline_formset([]),
        'organization_metadata_admins': inline_formset([]),
    })


def test_copy_creates_new_organization(client, two_tenants):
    plan_a, _plan_b, _dept_b, _person_b, _indicator_b, admin_a = two_tenants
    source = OrganizationFactory.create(
        parent=plan_a.organization,
        founding_date=datetime.date(2001, 2, 3),
        logo=AplansImageFactory.create(),
        distinct_name='Source distinct name',
    )
    client.force_login(admin_a)
    url = reverse(COPY_URL, args=(source.pk,))

    response = client.get(url)
    assert response.status_code == 200
    form = response.context['form']
    assert form.instance.pk is None
    assert form.initial['name'] == source.name
    assert form.fields['parent'].initial == plan_a.organization
    # The browser submits the form to its action, which must be this view and not the add view.
    assert f'action="{url}"' in response.content.decode()

    response = client.post(url, copy_form_data('Copy', parent=plan_a.organization))

    assert response.status_code == 302
    copy = Organization.objects.get(name='Copy')
    assert copy.pk != source.pk
    assert copy.uuid != source.uuid
    assert copy.get_parent() == plan_a.organization
    # Copied fields that the form does not show are kept; source-specific ones are not.
    assert copy.classification == source.classification
    assert copy.founding_date == source.founding_date
    assert copy.logo is None
    assert copy.distinct_name != source.distinct_name
    source_before = source.name
    source.refresh_from_db()
    assert source.name == source_before
    assert plan_a.organization.get_children().count() == 2


def test_copy_does_not_modify_other_tenants_organization(client, two_tenants):
    plan_a, plan_b, dept_b, person_b, indicator_b, admin_a = two_tenants
    name_before = dept_b.name
    client.force_login(admin_a)

    response = client.post(reverse(COPY_URL, args=(dept_b.pk,)), copy_form_data('Copy', parent=None))

    assert response.status_code == 302
    dept_b.refresh_from_db()
    assert dept_b.name == name_before
    assert dept_b.get_parent() == plan_b.organization
    assert Person.objects.filter(pk=person_b.pk, organization=dept_b).exists()
    assert Indicator.objects.filter(pk=indicator_b.pk, organization=dept_b).exists()
    copy = Organization.objects.get(name='Copy')
    assert copy.is_root()
    assert plan_a.related_organizations.filter(pk=copy.pk).exists()


def test_copy_cannot_place_organization_in_other_tenants_tree(client, two_tenants):
    _plan_a, plan_b, dept_b, _person_b, _indicator_b, admin_a = two_tenants
    client.force_login(admin_a)
    url = reverse(COPY_URL, args=(dept_b.pk,))

    response = client.get(url)
    assert plan_b.organization not in response.context['form'].fields['parent'].queryset

    response = client.post(url, copy_form_data('Copy', parent=plan_b.organization))

    assert response.status_code == 200
    assert 'parent' in response.context['form'].errors
    assert not Organization.objects.filter(name='Copy').exists()
    assert plan_b.organization.get_children().count() == 1


def test_copy_does_not_touch_source_admin_rows(client, two_tenants):
    """Inline rows posted with the id of one of the source's admin rows must not modify that row."""
    _plan_a, plan_b, dept_b, _person_b, _indicator_b, admin_a = two_tenants
    metadata_admin = PersonFactory.create(organization=plan_b.organization)
    row = OrganizationMetadataAdmin.objects.create(organization=dept_b, person=metadata_admin)
    other_person = PersonFactory.create()
    client.force_login(admin_a)

    data = copy_form_data('Copy', parent=None)
    data.update(
        nested_form_data({
            'organization_metadata_admins': inline_formset(
                [{'id': str(row.pk), 'person': str(other_person.pk)}],
                initial=1,
            ),
        })
    )
    client.post(reverse(COPY_URL, args=(dept_b.pk,)), data)

    row.refresh_from_db()
    assert row.organization == dept_b
    assert row.person == metadata_admin
    assert list(dept_b.organization_metadata_admins.all()) == [row]
