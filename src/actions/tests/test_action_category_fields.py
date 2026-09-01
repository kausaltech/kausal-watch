from django.urls import reverse

import pytest

from aplans.cache import PlanSpecificCache
from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import InstancesEditableByMixin

from actions.action_admin import ActionAdmin
from actions.models import Action
from actions.tests.factories import CategoryFactory, CategoryTypeFactory
from admin_site.tests.factories import ClientPlanFactory

pytestmark = pytest.mark.django_db


def _admin_request(rf, user, plan):
    request = rf.get('/')
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=plan)
    request.get_active_admin_plan = lambda: plan
    return request


def _form_fields(rf, user, action):
    request = _admin_request(rf, user, action.plan)
    with ctx_request.activate(request), ctx_instance.activate(action):
        edit_handler = ActionAdmin().get_edit_handler()
        return edit_handler.bind_to_model(Action).get_form_class().base_fields


def _field_panel_names(container):
    names = []
    for child in getattr(container, 'children', []):
        field_name = getattr(child, 'field_name', None)
        if field_name:
            names.append(field_name)
        names += _field_panel_names(child)
    return names


def _panel_field_names(rf, user, action):
    request = _admin_request(rf, user, action.plan)
    with ctx_request.activate(request), ctx_instance.activate(action):
        return _field_panel_names(ActionAdmin().get_edit_handler())


def _category_type(plan, editable_by):
    return CategoryTypeFactory.create(
        plan=plan,
        identifier='ct',
        editable_for_actions=True,
        instances_editable_by=editable_by,
    )


def test_category_field_is_shown_to_contact_person_when_editable_by_authenticated(rf, action, action_contact_person_user):
    _category_type(action.plan, InstancesEditableByMixin.EditableBy.AUTHENTICATED)
    assert 'categories_ct' in _form_fields(rf, action_contact_person_user, action)
    assert 'categories_ct' in _panel_field_names(rf, action_contact_person_user, action)


def test_category_field_is_hidden_from_contact_person_when_editable_by_plan_admins(rf, action, action_contact_person_user):
    _category_type(action.plan, InstancesEditableByMixin.EditableBy.PLAN_ADMINS)
    assert 'categories_ct' not in _form_fields(rf, action_contact_person_user, action)
    assert 'categories_ct' not in _panel_field_names(rf, action_contact_person_user, action)


def test_category_field_is_shown_to_plan_admin_when_editable_by_plan_admins(rf, action, plan_admin_user):
    _category_type(action.plan, InstancesEditableByMixin.EditableBy.PLAN_ADMINS)
    assert 'categories_ct' in _form_fields(rf, plan_admin_user, action)
    assert 'categories_ct' in _panel_field_names(rf, plan_admin_user, action)


def _post_action(client, user, action, extra_data):
    ClientPlanFactory.create(plan=action.plan)
    client.force_login(user)
    edit_url = reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})
    post_data = {
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'tasks-TOTAL_FORMS': '0',
        'tasks-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
        **extra_data,
    }
    return client.post(edit_url, data=post_data)


def test_contact_person_can_save_categories_editable_by_authenticated(client, action, action_contact_person_user):
    category_type = _category_type(action.plan, InstancesEditableByMixin.EditableBy.AUTHENTICATED)
    category = CategoryFactory.create(type=category_type)

    response = _post_action(client, action_contact_person_user, action, {'categories_ct': [str(category.pk)]})

    assert response.status_code == 302
    assert list(action.categories.all()) == [category]


def test_contact_person_cannot_save_categories_editable_by_plan_admins(client, action, action_contact_person_user):
    category_type = _category_type(action.plan, InstancesEditableByMixin.EditableBy.PLAN_ADMINS)
    category = CategoryFactory.create(type=category_type)

    response = _post_action(client, action_contact_person_user, action, {'categories_ct': [str(category.pk)]})

    assert response.status_code == 302
    assert list(action.categories.all()) == []
