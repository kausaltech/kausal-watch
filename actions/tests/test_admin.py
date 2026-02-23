from __future__ import annotations

import typing
from unittest.mock import Mock

from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

import pytest
from pytest_django.asserts import assertContains

from actions.action_admin import ActionAdmin
from actions.attribute_type_admin import AttributeTypeAdmin
from actions.tests.factories import (
    ActionFactory,
    AttributeTypeFactory,
    CategoryTypeFactory,
    PlanFactory,
)
from actions.wagtail_admin import PlanIndexView, PlanViewSet
from admin_site.tests.factories import ClientPlanFactory

if typing.TYPE_CHECKING:
    from actions.models import Action
    from conftest import ModelAdminEditTest
    from people.models import Person
    from users.models import User

pytestmark = pytest.mark.django_db


def get_request(rf, user=None, view_name='wagtailadmin_home', url=None):
    if url is None:
        url = reverse(view_name)
    request = rf.get(url)
    if user is not None:
        request.user = user
    return request


def get_plan_index_view(rf, client, user, view_set=None) -> PlanIndexView:
    if view_set is None:
        view_set = PlanViewSet()
    client.force_login(user)
    request = get_request(rf, user)
    index_view = PlanIndexView(**view_set.get_common_view_kwargs(), **view_set.get_index_view_kwargs())
    index_view.setup(request)
    return index_view


def edit_button_shown(rf, client, user, plan) -> bool:
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, user, view_set)
    buttons = index_view.get_list_buttons(user.get_active_admin_plan())
    edit_url_name = view_set.get_url_name('edit')
    return any(
        any(b.url == reverse(edit_url_name, args=[plan.pk]) for b in getattr(button, 'dropdown_buttons', []))
        for button in buttons
    )


@pytest.mark.parametrize("user__is_staff", [False])
def test_no_access_for_non_staff_user(user, client):
    client.force_login(user)
    response = client.get(reverse('wagtailadmin_home'), follow=True)
    assertContains(response, "You do not have permission to access the admin")


def test_login_removes_user_from_staff_if_no_plan_admin(user, client):
    assert user.is_staff
    assert not user.get_adminable_plans()
    client.force_login(user)
    user.refresh_from_db()
    assert not user.is_staff


def test_plan_edit_button_shown_to_superuser(rf, client, superuser, plan):
    assert edit_button_shown(rf, client, superuser, plan)


def test_plan_edit_button_shown_to_plan_admin(rf, client, plan_admin_user, plan):
    assert edit_button_shown(rf, client, plan_admin_user, plan)


def test_plan_edit_button_not_shown_to_action_contact_person(rf, client, action_contact_person_user, plan):
    assert not edit_button_shown(rf, client, action_contact_person_user, plan)


def test_superuser_can_list_plans(rf, superuser, plan, client):
    other_plan = PlanFactory.create()
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, superuser, view_set)
    qs = index_view.get_queryset()
    assert plan in qs
    assert other_plan in qs


def test_admin_can_list_only_own_plan(rf, plan, plan_admin_user, client):
    other_plan = PlanFactory.create()
    view_set = PlanViewSet()
    index_view = get_plan_index_view(rf, client, plan_admin_user, view_set)
    qs = index_view.get_queryset()
    assert plan in qs
    assert other_plan not in qs


def test_can_access_plan_edit_page(plan, plan_admin_user, client):
    ClientPlanFactory.create(plan=plan)
    view_set = PlanViewSet()
    edit_url_name = view_set.get_url_name('edit')
    url = reverse(edit_url_name, args=[plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    assert response.status_code == 200


def test_cannot_access_other_plan_edit_page(plan, plan_admin_user, client):
    other_plan = PlanFactory.create()
    view_set = PlanViewSet()
    edit_url_name = view_set.get_url_name('edit')
    url = reverse(edit_url_name, args=[other_plan.pk])
    client.force_login(plan_admin_user)
    response = client.get(url)
    # Wagtail doesn't respond with HTTP status 403 but with a redirect and an error message in a cookie.
    view_set.permission_policy.user_has_permission_for_instance(plan_admin_user, 'edit', plan)
    assert response.status_code == 302
    assert response.url == reverse('wagtailadmin_home')


def test_action_admin(
    plan_admin_user: User, action_contact_person: Person, action: Action,
    test_modeladmin_edit: ModelAdminEditTest,
):
    ClientPlanFactory(plan=action.plan)
    post_data = dict(name='Modified name', identifier=action.identifier)
    test_modeladmin_edit(
        ActionAdmin, action, plan_admin_user, post_data=post_data, can_inspect=True, can_edit=True,
    )
    return
    # FIXME
    action.refresh_from_db()
    #assert action.name == post_data['name']
    test_modeladmin_edit(
        ActionAdmin, action, action_contact_person.user, post_data=post_data, can_inspect=True, can_edit=True,
    )
    other_action = ActionFactory.create(plan=action.plan)
    test_modeladmin_edit(
        ActionAdmin, other_action, plan_admin_user, post_data=post_data, can_inspect=True, can_edit=True,
    )
    test_modeladmin_edit(
        ActionAdmin, other_action, action_contact_person.user, post_data=post_data, can_inspect=True, can_edit=False,
    )


class TestAttributeTypeAdminQueryset:
    """Tests for AttributeTypeAdmin.get_queryset filtering based on community engagement feature."""

    @pytest.fixture
    def action_attribute_type(self, plan):
        """Create an attribute type for actions scoped to the plan."""
        action_ct = ContentType.objects.get(app_label='actions', model='action')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        return AttributeTypeFactory.create(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            name='Action Attribute',
        )

    @pytest.fixture
    def category_attribute_type(self, plan):
        """Create an attribute type for categories scoped to a category type."""
        category_ct = ContentType.objects.get(app_label='actions', model='category')
        category_type_ct = ContentType.objects.get(app_label='actions', model='categorytype')
        category_type = CategoryTypeFactory.create(plan=plan)
        return AttributeTypeFactory.create(
            object_content_type=category_ct,
            scope_content_type=category_type_ct,
            scope_id=category_type.id,
            name='Category Attribute',
        )

    @pytest.fixture
    def pledge_attribute_type(self, plan):
        """Create an attribute type for pledges scoped to the plan."""
        pledge_ct = ContentType.objects.get(app_label='actions', model='pledge')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        return AttributeTypeFactory.create(
            object_content_type=pledge_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            name='Pledge Attribute',
        )

    def test_pledge_attribute_types_excluded_when_community_engagement_disabled(
        self, rf, plan, plan_admin_user,
        action_attribute_type, category_attribute_type, pledge_attribute_type,
    ):
        """Pledge attribute types should not appear when community engagement is disabled."""
        plan.features.enable_community_engagement = False
        plan.features.save()

        admin = AttributeTypeAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        qs = admin.get_queryset(request)

        assert action_attribute_type in qs
        assert category_attribute_type in qs
        assert pledge_attribute_type not in qs

    def test_pledge_attribute_types_included_when_community_engagement_enabled(
        self, rf, plan, plan_admin_user,
        action_attribute_type, category_attribute_type, pledge_attribute_type,
    ):
        """Pledge attribute types should appear when community engagement is enabled."""
        plan.features.enable_community_engagement = True
        plan.features.save()

        admin = AttributeTypeAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        qs = admin.get_queryset(request)

        assert action_attribute_type in qs
        assert category_attribute_type in qs
        assert pledge_attribute_type in qs


class TestAttributeTypeAdminButtonHelper:
    """Tests for AttributeTypeAdminButtonHelper preserving content_type parameter."""

    @pytest.fixture
    def attribute_type(self, plan):
        """Create an attribute type for testing."""
        action_ct = ContentType.objects.get(app_label='actions', model='action')
        plan_ct = ContentType.objects.get(app_label='actions', model='plan')
        return AttributeTypeFactory.create(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
            name='Test Attribute',
        )

    def test_add_button_shown_with_content_type_parameter(
        self, rf, plan, plan_admin_user, attribute_type
    ):
        """Add button should be shown when content_type parameter is present."""
        from actions.attribute_type_admin import AttributeTypeAdmin, AttributeTypeAdminButtonHelper

        admin = AttributeTypeAdmin()
        request = rf.get(f'/admin/?content_type={attribute_type.object_content_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.url_helper.create_url = '/admin/create/'
        view.permission_helper = Mock()

        helper = AttributeTypeAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is not None
        assert f'content_type={attribute_type.object_content_type.id}' in result['url']

    def test_add_button_hidden_without_content_type_parameter(self, rf, plan, plan_admin_user):
        """Add button should be hidden when content_type parameter is missing."""
        from actions.attribute_type_admin import AttributeTypeAdmin, AttributeTypeAdminButtonHelper

        admin = AttributeTypeAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.permission_helper = Mock()

        helper = AttributeTypeAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is None

    def test_edit_button_preserves_content_type_parameter(
        self, rf, plan, plan_admin_user, attribute_type
    ):
        """Edit button should preserve content_type parameter in URL."""
        from actions.attribute_type_admin import AttributeTypeAdminButtonHelper

        request = rf.get(f'/admin/?content_type={attribute_type.object_content_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = AttributeTypeFactory._meta.model
        view.url_helper = Mock()
        view.url_helper.get_action_url = Mock(
            side_effect=lambda action, pk: f'/admin/{action}/{pk}/'
        )
        view.permission_helper = Mock()

        helper = AttributeTypeAdminButtonHelper(view, request)
        result = helper.edit_button(pk=attribute_type.id)

        assert result is not None
        assert f'content_type={attribute_type.object_content_type.id}' in result['url']


class TestCategoryAdminButtonHelper:
    """Tests for CategoryAdminButtonHelper preserving category_type parameter."""

    @pytest.fixture
    def category_type(self, plan):
        """Create a category type for testing."""
        return CategoryTypeFactory.create(plan=plan, name='Test Category Type')

    def test_add_button_shown_with_category_type_parameter(
        self, rf, plan, plan_admin_user, category_type
    ):
        """Add button should be shown when category_type parameter is present."""
        from actions.category_admin import CategoryAdmin, CategoryAdminButtonHelper

        admin = CategoryAdmin()
        request = rf.get(f'/admin/?category_type={category_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.url_helper.create_url = '/admin/create/'
        view.permission_helper = Mock()

        helper = CategoryAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is not None
        assert f'category_type={category_type.id}' in result['url']

    def test_add_button_hidden_without_category_type_parameter(self, rf, plan, plan_admin_user):
        """Add button should be hidden when category_type parameter is missing."""
        from actions.category_admin import CategoryAdmin, CategoryAdminButtonHelper

        admin = CategoryAdmin()
        request = rf.get('/admin/')
        request.user = plan_admin_user

        view = Mock()
        view.model = admin.model
        view.url_helper = Mock()
        view.permission_helper = Mock()

        helper = CategoryAdminButtonHelper(view, request)
        result = helper.add_button()

        assert result is None

    def test_inspect_button_preserves_category_type_parameter(
        self, rf, plan, plan_admin_user, category_type
    ):
        """Inspect button should preserve category_type parameter in URL."""
        from actions.category_admin import CategoryAdminButtonHelper

        request = rf.get(f'/admin/?category_type={category_type.id}')
        request.user = plan_admin_user

        view = Mock()
        view.model = CategoryTypeFactory._meta.model
        view.url_helper = Mock()
        view.url_helper.get_action_url = Mock(
            side_effect=lambda action, pk: f'/admin/{action}/{pk}/'
        )
        view.permission_helper = Mock()

        helper = CategoryAdminButtonHelper(view, request)
        result = helper.inspect_button(pk=category_type.id)

        assert result is not None
        assert f'category_type={category_type.id}' in result['url']


def test_action_responsible_party_swap_should_succeed(plan_admin_user, action, client):
    """
    Test that swapping organizations between ActionResponsibleParty instances works correctly.

    When swapping organizations between different roles (e.g., org A moves from primary
    to collaborator, org B moves from collaborator to primary), the final state has
    each organization appearing only once, so this should be a valid operation.

    This test currently FAILS due to a bug where Django's ORM saves formsets sequentially,
    causing a temporary duplicate violation of the unique_together constraint.
    After the fix, the swap should succeed without errors.
    """
    from actions.action_admin import ActionAdmin
    from actions.models import ActionResponsibleParty
    from actions.tests.factories import ActionResponsiblePartyFactory
    from admin_site.tests.factories import ClientPlanFactory
    from orgs.tests.factories import OrganizationFactory

    # Setup: Create the plan's client association
    ClientPlanFactory.create(plan=action.plan)

    # Create two organizations
    org_a = OrganizationFactory.create()
    org_b = OrganizationFactory.create()

    # Create two ActionResponsibleParty records with different organizations and roles
    # Initial state: org_a is PRIMARY, org_b is COLLABORATOR
    arp_primary = ActionResponsiblePartyFactory.create(
        action=action,
        organization=org_a,
        role=ActionResponsibleParty.Role.PRIMARY,
    )
    arp_collaborator = ActionResponsiblePartyFactory.create(
        action=action,
        organization=org_b,
        role=ActionResponsibleParty.Role.COLLABORATOR,
    )

    # Get the edit URL for the action
    admin = ActionAdmin()
    edit_url_name = admin.url_helper.get_action_url_name('edit')
    edit_url = reverse(edit_url_name, kwargs={'instance_pk': action.pk})

    # Login as plan admin
    client.force_login(plan_admin_user)

    # Construct POST data that swaps the organizations between the two roles
    # Desired state: org_b is PRIMARY, org_a is COLLABORATOR
    post_data = {
        # Required action fields
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',  # Required field
        # Primary responsible parties formset - swap to org B
        'responsible_parties_primary-TOTAL_FORMS': '1',
        'responsible_parties_primary-INITIAL_FORMS': '1',
        'responsible_parties_primary-MIN_NUM_FORMS': '0',
        'responsible_parties_primary-MAX_NUM_FORMS': '1000',
        'responsible_parties_primary-0-id': arp_primary.pk,
        'responsible_parties_primary-0-organization': org_b.pk,  # Swapped from org_a
        'responsible_parties_primary-0-ORDER': '1',
        # Collaborator responsible parties formset - swap to org A
        'responsible_parties_collaborator-TOTAL_FORMS': '1',
        'responsible_parties_collaborator-INITIAL_FORMS': '1',
        'responsible_parties_collaborator-MIN_NUM_FORMS': '0',
        'responsible_parties_collaborator-MAX_NUM_FORMS': '1000',
        'responsible_parties_collaborator-0-id': arp_collaborator.pk,
        'responsible_parties_collaborator-0-organization': org_a.pk,  # Swapped from org_b
        'responsible_parties_collaborator-0-ORDER': '1',
        # Empty formsets for other relations (required for form validation)
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
    }

    # Execute the POST request - this should succeed with a redirect
    response = client.post(edit_url, data=post_data)

    # Verify successful save (redirect to the action list or detail page)
    assert response.status_code == 302, f"Expected redirect, got {response.status_code}"

    # Query for the responsible parties after the swap
    # Note: The delete-recreate approach means the old PKs no longer exist,
    # so we need to query by organization
    responsible_parties = ActionResponsibleParty.objects.filter(action=action)
    assert responsible_parties.count() == 2, "Should have exactly 2 responsible parties"

    # Find the parties by organization
    party_with_org_a = responsible_parties.get(organization=org_a)
    party_with_org_b = responsible_parties.get(organization=org_b)

    # Verify the organizations have been swapped to the correct roles
    assert party_with_org_b.role == ActionResponsibleParty.Role.PRIMARY, \
        f"org_b should now be PRIMARY, but has role {party_with_org_b.role}"

    assert party_with_org_a.role == ActionResponsibleParty.Role.COLLABORATOR, \
        f"org_a should now be COLLABORATOR, but has role {party_with_org_a.role}"


def test_action_responsible_party_swap_on_publish_draft(plan, organization_factory, action_factory):
    """
    Test that publishing a Wagtail draft revision with swapped responsible parties succeeds.

    This tests the code path where Wagtail deserializes a revision (via revision.as_object())
    and then saves it (via Action.save()). The deserialized action will have child objects
    with existing PKs but swapped organizations, which would cause an IntegrityError without
    the fix in Action.save().
    """
    from actions.models import ActionResponsibleParty

    # Create two organizations
    org_a = organization_factory()
    org_b = organization_factory()

    # Create an action with two responsible parties in initial state
    action = action_factory(plan=plan)
    ActionResponsibleParty.objects.create(
        action=action,
        organization=org_a,
        role=ActionResponsibleParty.Role.PRIMARY,
        order=0,
    )
    ActionResponsibleParty.objects.create(
        action=action,
        organization=org_b,
        role=ActionResponsibleParty.Role.COLLABORATOR,
        order=1,
    )

    # Create an initial revision (don't publish yet - we'll test publishing the swapped one)
    initial_revision = action.save_revision()

    # Now manually create a revision with swapped responsible parties
    # Get the revision content and modify it to have the swap
    # Note: Use initial_revision.content (dict) not content_json (string)
    revision_content = initial_revision.content.copy()

    # Ensure attributes key exists (required by Action.publish())
    # This is needed because Action.publish() expects it
    if 'attributes' not in revision_content:
        revision_content['attributes'] = {}

    # Find the responsible_parties in the revision content
    # The structure is: revision_content['responsible_parties'] = [list of dicts]
    # Each dict has keys: 'pk', 'order', 'action', 'organization', 'role', 'specifier'
    responsible_parties = revision_content.get('responsible_parties', [])

    # Swap the organizations while keeping the PKs
    for rp in responsible_parties:
        if rp.get('organization') == org_a.pk:
            # This was org_a (PRIMARY), swap to org_b
            rp['organization'] = org_b.pk
        elif rp.get('organization') == org_b.pk:
            # This was org_b (COLLABORATOR), swap to org_a
            rp['organization'] = org_a.pk

    # Create a new revision with the swapped content
    from wagtail.models import Revision
    swapped_revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    swapped_revision.content = revision_content
    swapped_revision.save()

    # Verify current published state is still the original (before swap)
    action.refresh_from_db()
    parties_before = ActionResponsibleParty.objects.filter(action=action)
    assert parties_before.count() == 2
    assert parties_before.get(organization=org_a).role == ActionResponsibleParty.Role.PRIMARY
    assert parties_before.get(organization=org_b).role == ActionResponsibleParty.Role.COLLABORATOR

    # Now publish the revision with swapped responsible parties
    # This should NOT raise IntegrityError
    swapped_revision.publish()

    # Verify the swap was applied successfully
    action.refresh_from_db()
    parties_after = ActionResponsibleParty.objects.filter(action=action)
    assert parties_after.count() == 2

    party_a_after = parties_after.get(organization=org_a)
    party_b_after = parties_after.get(organization=org_b)

    # Verify the organizations have been swapped to the correct roles
    assert party_b_after.role == ActionResponsibleParty.Role.PRIMARY
    assert party_a_after.role == ActionResponsibleParty.Role.COLLABORATOR


def test_action_contact_person_swap_should_succeed(plan_admin_user, action, client):
    """
    Test that swapping persons between ActionContactPerson instances works correctly.

    When swapping persons between different roles (e.g., person A moves from editor
    to moderator, person B moves from moderator to editor), the final state has
    each person appearing only once, so this should be a valid operation.

    This tests the renormalization logic in ActionAdminForm._renormalize_pks_for_swaps().
    """
    from actions.action_admin import ActionAdmin
    from actions.models import ActionContactPerson
    from actions.tests.factories import ActionContactFactory
    from admin_site.tests.factories import ClientPlanFactory
    from people.tests.factories import PersonFactory

    # Setup: Create the plan's client association
    ClientPlanFactory.create(plan=action.plan)

    # Create two persons
    person_a = PersonFactory.create()
    person_b = PersonFactory.create()

    # Create two ActionContactPerson records with different persons and roles
    # Initial state: person_a is EDITOR, person_b is MODERATOR
    acp_editor = ActionContactFactory.create(
        action=action,
        person=person_a,
        role=ActionContactPerson.Role.EDITOR,
    )
    acp_moderator = ActionContactFactory.create(
        action=action,
        person=person_b,
        role=ActionContactPerson.Role.MODERATOR,
    )

    # Get the edit URL for the action
    admin = ActionAdmin()
    edit_url_name = admin.url_helper.get_action_url_name('edit')
    edit_url = reverse(edit_url_name, kwargs={'instance_pk': action.pk})

    # Login as plan admin
    client.force_login(plan_admin_user)

    # Construct POST data that swaps the persons between the two roles
    # Desired state: person_b is EDITOR, person_a is MODERATOR
    post_data = {
        # Required action fields
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',  # Required field
        # Editor contact persons formset - swap to person B
        'contact_persons_editor-TOTAL_FORMS': '1',
        'contact_persons_editor-INITIAL_FORMS': '1',
        'contact_persons_editor-MIN_NUM_FORMS': '0',
        'contact_persons_editor-MAX_NUM_FORMS': '1000',
        'contact_persons_editor-0-id': acp_editor.pk,
        'contact_persons_editor-0-person': person_b.pk,  # Swapped from person_a
        'contact_persons_editor-0-ORDER': '1',
        # Moderator contact persons formset - swap to person A
        'contact_persons_moderator-TOTAL_FORMS': '1',
        'contact_persons_moderator-INITIAL_FORMS': '1',
        'contact_persons_moderator-MIN_NUM_FORMS': '0',
        'contact_persons_moderator-MAX_NUM_FORMS': '1000',
        'contact_persons_moderator-0-id': acp_moderator.pk,
        'contact_persons_moderator-0-person': person_a.pk,  # Swapped from person_b
        'contact_persons_moderator-0-ORDER': '1',
        # Empty formsets for other relations (required for form validation)
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
    }

    # Execute the POST request - this should succeed with a redirect
    response = client.post(edit_url, data=post_data)

    # Verify successful save (redirect to the action list or detail page)
    assert response.status_code == 302, f"Expected redirect, got {response.status_code}"

    # Query for the contact persons after the swap
    contact_persons = ActionContactPerson.objects.filter(action=action)
    assert contact_persons.count() == 2, "Should have exactly 2 contact persons"

    # Find the contacts by person
    contact_with_person_a = contact_persons.get(person=person_a)
    contact_with_person_b = contact_persons.get(person=person_b)

    # Verify the persons have been swapped to the correct roles
    assert contact_with_person_b.role == ActionContactPerson.Role.EDITOR, \
        f"person_b should now be EDITOR, but has role {contact_with_person_b.role}"

    assert contact_with_person_a.role == ActionContactPerson.Role.MODERATOR, \
        f"person_a should now be MODERATOR, but has role {contact_with_person_a.role}"


def test_action_contact_person_swap_on_publish_draft(plan, person_factory, action_factory):
    """
    Test that publishing a Wagtail draft revision with swapped contact persons succeeds.

    This tests the code path where Wagtail deserializes a revision (via revision.as_object())
    and then publishes it (via Action.publish()). The deserialized action will have child objects
    with existing PKs but swapped persons, which would cause an IntegrityError without
    the fix in Action._renormalize_revision_items().
    """
    from actions.models import ActionContactPerson

    # Create two persons
    person_a = person_factory()
    person_b = person_factory()

    # Create an action with two contact persons in initial state
    action = action_factory(plan=plan)
    ActionContactPerson.objects.create(
        action=action,
        person=person_a,
        role=ActionContactPerson.Role.EDITOR,
        order=0,
    )
    ActionContactPerson.objects.create(
        action=action,
        person=person_b,
        role=ActionContactPerson.Role.MODERATOR,
        order=1,
    )

    # Create an initial revision (don't publish yet - we'll test publishing the swapped one)
    initial_revision = action.save_revision()

    # Now manually create a revision with swapped contact persons
    # Get the revision content and modify it to have the swap
    revision_content = initial_revision.content.copy()

    # Ensure attributes key exists (required by Action.publish())
    if 'attributes' not in revision_content:
        revision_content['attributes'] = {}

    # Find the contact_persons in the revision content
    # The structure is: revision_content['contact_persons'] = [list of dicts]
    # Each dict has keys: 'pk', 'order', 'action', 'person', 'role', 'primary_contact'
    contact_persons = revision_content.get('contact_persons', [])

    # Swap the persons while keeping the PKs
    for cp in contact_persons:
        if cp.get('person') == person_a.pk:
            # This was person_a (EDITOR), swap to person_b
            cp['person'] = person_b.pk
        elif cp.get('person') == person_b.pk:
            # This was person_b (MODERATOR), swap to person_a
            cp['person'] = person_a.pk

    # Create a new revision with the swapped content
    from wagtail.models import Revision
    swapped_revision: Revision = Revision(
        content_type=initial_revision.content_type,
        base_content_type=initial_revision.base_content_type,
        object_id=action.pk,
    )
    swapped_revision.content = revision_content
    swapped_revision.save()

    # Verify current published state is still the original (before swap)
    action.refresh_from_db()
    contacts_before = ActionContactPerson.objects.filter(action=action)
    assert contacts_before.count() == 2
    assert contacts_before.get(person=person_a).role == ActionContactPerson.Role.EDITOR
    assert contacts_before.get(person=person_b).role == ActionContactPerson.Role.MODERATOR

    # Now publish the revision with swapped contact persons
    # This should NOT raise IntegrityError
    swapped_revision.publish()

    # Verify the swap was applied successfully
    action.refresh_from_db()
    contacts_after = ActionContactPerson.objects.filter(action=action)
    assert contacts_after.count() == 2

    contact_a_after = contacts_after.get(person=person_a)
    contact_b_after = contacts_after.get(person=person_b)

    # Verify the persons have been swapped to the correct roles
    assert contact_b_after.role == ActionContactPerson.Role.EDITOR
    assert contact_a_after.role == ActionContactPerson.Role.MODERATOR
