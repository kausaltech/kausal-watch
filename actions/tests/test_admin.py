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
