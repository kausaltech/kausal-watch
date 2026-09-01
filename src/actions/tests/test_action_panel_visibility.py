import pytest

from aplans.cache import PlanSpecificCache
from aplans.context_vars import ctx_instance, ctx_request
from aplans.utils import InstancesEditableByMixin, InstancesVisibleForMixin

from actions.action_admin import ActionAdmin
from actions.models import Action
from admin_site.tests.factories import BuiltInFieldCustomizationFactory

pytestmark = pytest.mark.django_db


def _admin_request(rf, user, plan):
    request = rf.get('/')
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=plan)
    request.get_active_admin_plan = lambda: plan
    return request


def _get_edit_handler(rf, user, action):
    request = _admin_request(rf, user, action.plan)
    with ctx_request.activate(request), ctx_instance.activate(action):
        return ActionAdmin().get_edit_handler()


def _tab_headings(edit_handler):
    return [str(tab.heading) for tab in edit_handler.children]


def _formsets(rf, user, action):
    request = _admin_request(rf, user, action.plan)
    with ctx_request.activate(request), ctx_instance.activate(action):
        edit_handler = ActionAdmin().get_edit_handler()
        return edit_handler.bind_to_model(Action).get_form_class().formsets


def _restrict(action, field_name):
    BuiltInFieldCustomizationFactory.create(
        plan=action.plan,
        field_name=field_name,
        instances_visible_for=InstancesVisibleForMixin.VisibleFor.PLAN_ADMINS,
        instances_editable_by=InstancesEditableByMixin.EditableBy.NOT_EDITABLE,
    )


def _find_relation_panel(container, relation_name):
    for child in getattr(container, 'children', []):
        if getattr(child, 'relation_name', None) == relation_name:
            return child
        found = _find_relation_panel(child, relation_name)
        if found is not None:
            return found
    return None


def _is_shown(panel, rf, user, action):
    request = _admin_request(rf, user, action.plan)
    with ctx_request.activate(request), ctx_instance.activate(action):
        bound = panel.bind_to_model(Action).get_bound_panel(instance=action, request=request, form=None)
        return bound.is_shown()


def _tasks_heading(action):
    return str(action.plan.general_content.get_action_task_term_display_plural())


def test_tasks_tab_is_shown_without_customization(rf, action, action_contact_person_user):
    edit_handler = _get_edit_handler(rf, action_contact_person_user, action)
    assert _tasks_heading(action) in _tab_headings(edit_handler)
    assert 'tasks' in _formsets(rf, action_contact_person_user, action)


def test_tasks_tab_is_hidden_for_restricted_user(rf, action, action_contact_person_user):
    _restrict(action, 'tasks')
    edit_handler = _get_edit_handler(rf, action_contact_person_user, action)
    assert _tasks_heading(action) not in _tab_headings(edit_handler)
    assert 'tasks' not in _formsets(rf, action_contact_person_user, action)


def test_tasks_tab_is_shown_for_plan_admin(rf, action, plan_admin_user):
    _restrict(action, 'tasks')
    edit_handler = _get_edit_handler(rf, plan_admin_user, action)
    assert _tasks_heading(action) in _tab_headings(edit_handler)


@pytest.mark.parametrize('field_name', ['contact_persons', 'responsible_parties'])
def test_role_panel_is_hidden_for_restricted_user(rf, action, action_contact_person_user, field_name):
    _restrict(action, field_name)
    edit_handler = _get_edit_handler(rf, action_contact_person_user, action)
    panel = _find_relation_panel(edit_handler, field_name)
    assert panel is not None
    assert not _is_shown(panel, rf, action_contact_person_user, action)


@pytest.mark.parametrize('field_name', ['contact_persons', 'responsible_parties'])
def test_role_panel_is_shown_for_plan_admin(rf, action, plan_admin_user, field_name):
    _restrict(action, field_name)
    edit_handler = _get_edit_handler(rf, plan_admin_user, action)
    panel = _find_relation_panel(edit_handler, field_name)
    assert panel is not None
    assert _is_shown(panel, rf, plan_admin_user, action)


def test_existing_tasks_survive_saving_when_tasks_are_hidden(client, action, action_contact_person_user):
    """Posting the edit form without a tasks formset must not delete the action's tasks."""
    from django.urls import reverse

    from actions.tests.factories import ActionTaskFactory
    from admin_site.tests.factories import ClientPlanFactory

    ClientPlanFactory.create(plan=action.plan)
    task = ActionTaskFactory.create(action=action)
    _restrict(action, 'tasks')
    client.force_login(action_contact_person_user)
    edit_url = reverse(ActionAdmin().url_helper.get_action_url_name('edit'), kwargs={'instance_pk': action.pk})
    post_data = {
        'identifier': action.identifier,
        'name': action.name,
        'visibility': 'public',
        'links-TOTAL_FORMS': '0',
        'links-INITIAL_FORMS': '0',
        'contact_persons_editor-TOTAL_FORMS': '0',
        'contact_persons_editor-INITIAL_FORMS': '0',
        'contact_persons_moderator-TOTAL_FORMS': '0',
        'contact_persons_moderator-INITIAL_FORMS': '0',
        'responsible_parties_primary-TOTAL_FORMS': '0',
        'responsible_parties_primary-INITIAL_FORMS': '0',
        'responsible_parties_collaborator-TOTAL_FORMS': '0',
        'responsible_parties_collaborator-INITIAL_FORMS': '0',
    }

    response = client.post(edit_url, data=post_data)

    assert response.status_code == 302
    assert list(action.tasks.all()) == [task]
