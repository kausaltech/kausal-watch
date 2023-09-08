from django.urls import reverse
import pytest

from admin_site.models import Client
from actions.tests.factories import ActionContactFactory, ActionResponsiblePartyFactory, PlanFactory
from indicators.tests.factories import IndicatorContactFactory, IndicatorLevelFactory
from people.tests.factories import PersonFactory
from orgs.tests.factories import OrganizationFactory, OrganizationPlanAdminFactory
from admin_site.tests.factories import ClientPlanFactory, EmailDomainsFactory


pytestmark = pytest.mark.django_db


def test_is_contact_person_for_action():
    contact = ActionContactFactory()
    user = contact.person.user
    action = contact.action
    assert user.is_contact_person_for_action()
    assert user.is_contact_person_for_action(action)


def test_is_contact_person_for_action_false(user, action):
    assert not user.is_contact_person_for_action()
    assert not user.is_contact_person_for_action(action)


def test_is_contact_person_for_indicator():
    contact = IndicatorContactFactory()
    user = contact.person.user
    indicator = contact.indicator
    assert user.is_contact_person_for_indicator()
    assert user.is_contact_person_for_indicator(indicator)


def test_is_contact_person_for_indicator_false(user, indicator):
    assert not user.is_contact_person_for_indicator()
    assert not user.is_contact_person_for_indicator(indicator)


def test_is_contact_person_for_action_in_plan():
    contact = ActionContactFactory()
    user = contact.person.user
    action = contact.action
    assert user.is_contact_person_for_action_in_plan(action.plan)
    assert user.is_contact_person_for_action_in_plan(action.plan, action)


def test_is_contact_person_for_action_in_plan_false(user, action):
    assert not user.is_contact_person_for_action_in_plan(action.plan)
    assert not user.is_contact_person_for_action_in_plan(action.plan, action)


def test_is_contact_person_for_action_in_plan_false_other_plan(user):
    contact = ActionContactFactory()
    user = contact.person.user
    action = contact.action
    other_plan = PlanFactory()
    assert not user.is_contact_person_for_action_in_plan(other_plan)
    assert not user.is_contact_person_for_action_in_plan(other_plan, action)


def test_is_contact_person_for_indicator_in_plan():
    contact = IndicatorContactFactory()
    user = contact.person.user
    indicator = contact.indicator
    plan = IndicatorLevelFactory(indicator=indicator).plan
    assert user.is_contact_person_for_indicator_in_plan(plan)
    assert user.is_contact_person_for_indicator_in_plan(plan, indicator)


def test_is_contact_person_for_indicator_in_plan_false(user, indicator):
    plan = IndicatorLevelFactory(indicator=indicator).plan
    assert not user.is_contact_person_for_indicator_in_plan(plan)
    assert not user.is_contact_person_for_indicator_in_plan(plan, indicator)


def test_is_contact_person_for_indicator_in_plan_false_other_plan(user):
    contact = IndicatorContactFactory()
    user = contact.person.user
    indicator = contact.indicator
    IndicatorLevelFactory(indicator=indicator)
    other_plan = PlanFactory()
    assert not user.is_contact_person_for_indicator_in_plan(other_plan)
    assert not user.is_contact_person_for_indicator_in_plan(other_plan, indicator)


def test_is_general_admin_for_plan_superuser(superuser, plan):
    assert superuser.is_general_admin_for_plan()
    assert superuser.is_general_admin_for_plan(plan)


def test_is_general_admin_for_plan_false(user, plan):
    assert not user.is_general_admin_for_plan()
    assert not user.is_general_admin_for_plan(plan)


def test_is_general_admin_for_plan(plan_admin_user, plan):
    assert plan_admin_user.is_general_admin_for_plan()
    assert plan_admin_user.is_general_admin_for_plan(plan)


def test_is_organization_admin_for_action_false(user, action):
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action(action):
    org = action.plan.organization
    person = PersonFactory(organization=org)
    plan = action.plan
    OrganizationPlanAdminFactory(organization=org, person=person, plan=plan)
    ActionResponsiblePartyFactory(action=action, organization=org)
    user = person.user
    # User's organization is responsible party for action
    assert user.is_organization_admin_for_action()
    assert user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action_not_responsible(action):
    org = action.plan.organization
    person = PersonFactory(organization=org)
    plan = action.plan
    OrganizationPlanAdminFactory(organization=org, person=person, plan=plan)
    user = person.user
    # User is organization admin, but the user's organization is not a responsible party for the action
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_is_organization_admin_for_action_not_admin(action):
    org = action.plan.organization
    ActionResponsiblePartyFactory(action=action, organization=org)
    person = PersonFactory(organization=org)
    user = person.user
    # User's organization is responsible party but user is not organization admin
    assert not user.is_organization_admin_for_action()
    assert not user.is_organization_admin_for_action(action)


def test_get_adminable_organizations_superuser(superuser):
    organization = OrganizationFactory()
    assert organization in superuser.get_adminable_organizations().all()


def test_get_adminable_organizations_is_not_admin(user):
    organization = OrganizationFactory()
    assert organization not in user.get_adminable_organizations()


def test_get_adminable_organizations_descendants(superuser):
    organization = OrganizationFactory()
    sub_org = OrganizationFactory(parent=organization)
    adminable = superuser.get_adminable_organizations()
    assert organization in adminable
    assert sub_org in adminable


def test_get_adminable_organizations_organization_plan_admin():
    org_admin = OrganizationPlanAdminFactory()
    assert list(org_admin.person.user.get_adminable_organizations()) == [org_admin.organization]


def test_new_user_password_login_preconditions_met(plan, api_client, client, person_factory, action_contact_factory):
    cp = ClientPlanFactory(plan=plan)
    EmailDomainsFactory(client=cp.client)
    assert plan.clients.count() > 0
    for cp in plan.clients.all():
        assert cp.client.email_domains.count() > 0
    person = person_factory(email='foo@bar.xyz')
    assert person.email.split('@')[0] not in [eh.domain for eh in cp.client.email_domains.all()]
    user = person.user
    assert user.has_usable_password()
    email = user.email.capitalize()
    url = reverse('admin_check_login_method')
    action_contact_factory(person=person)
    response = api_client.post(url, {'email': email})
    data = response.json_data
    assert response.status_code == 200
    assert data['method'] == 'password'
    client.force_login(user)


def test_new_user_social_auth_login_preconditions_met(plan, api_client, client, person_factory, action_contact_factory):
    cp = ClientPlanFactory(plan=plan)
    assert cp.client.auth_backend == Client.AuthBackend.AZURE_AD
    EmailDomainsFactory(client=cp.client)
    assert plan.clients.count() > 0
    for cp in plan.clients.all():
        assert cp.client.email_domains.count() > 0
    email = f'user@{cp.client.email_domains.first().domain}'
    person = person_factory(email=email)
    user = person.user
    assert not user.has_usable_password()
    email = user.email.capitalize()
    url = reverse('admin_check_login_method')
    action_contact_factory(person=person)
    response = api_client.post(url, {'email': email})
    data = response.json_data
    assert response.status_code == 200
    assert data['method'] == 'azure_ad'
    client.force_login(user)
