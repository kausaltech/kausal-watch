"""What saving an action in the admin records, with and without a moderation workflow."""

from __future__ import annotations

from django.urls import reverse
from reversion.models import Version
from wagtail.admin.models import EditingSession

import pytest

from aplans.cache import PlanSpecificCache
from aplans.context_vars import ctx_request

from actions.action_admin import ActionViewSet
from actions.models import Action
from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory
from admin_site.tests.utils import post_data
from audit_logging.models import PlanScopedModelLogEntry

pytestmark = pytest.mark.django_db

CHANGE_LOG_FORM_URL = reverse('wagtailsnippets_actions_actionchangelogmessage:add')


@pytest.fixture
def plan():
    return PlanFactory.create()


@pytest.fixture
def moderated_plan():
    plan = PlanFactory.create()
    h.enable_moderation(plan)
    return plan


def log_entries(action: Action) -> list[PlanScopedModelLogEntry]:
    return list(PlanScopedModelLogEntry.objects.filter(object_id=str(action.pk)).order_by('id'))


def enable_change_log(plan) -> None:
    plan.features.enable_change_log = True
    plan.features.save()


def create_action(client, user, name: str = 'Created action'):
    client.force_login(user)
    data = post_data(client.get(h.create_url()).context['form'])
    data.update(name=name, identifier='created-1')
    response = client.post(h.create_url(), data=data)
    return response, Action.objects.get(name=name)


class TestWithoutModeration:
    def test_edit_page_offers_no_moderation_buttons(self, client, plan):
        action = ActionFactory.create(plan=plan)
        admin_menu = h.action_menu_names(h.get_edit_page(client, h.make_plan_admin(plan), action))
        contact_person_menu = h.action_menu_names(h.get_edit_page(client, h.make_contact_person(action), action))

        assert admin_menu == ['action-save', 'action-delete', '_continue']
        assert contact_person_menu == ['action-save', '_continue']

    @pytest.mark.parametrize('make_user', [h.plan_admin_for, h.make_contact_person])
    def test_save_is_live_at_once(self, client, plan, make_user):
        action = ActionFactory.create(plan=plan, name='Old name')
        user = make_user(action)

        response = h.post_edit(client, user, action, name='New name')

        assert response.status_code == 302
        assert response['Location'] == h.index_url()
        assert any('updated' in message for message in h.message_texts(response))
        action.refresh_from_db()
        assert action.name == 'New name'
        assert action.live
        assert not action.has_unpublished_changes

    def test_save_records_a_published_revision(self, client, plan):
        action = ActionFactory.create(plan=plan, name='Old name')
        user = h.make_plan_admin(plan)

        h.post_edit(client, user, action, name='New name')

        action.refresh_from_db()
        revision = action.revisions.get()
        assert revision.user == user
        assert revision.content['name'] == 'New name'
        assert action.latest_revision == revision
        assert action.live_revision == revision

    def test_save_records_an_audit_log_entry(self, client, plan):
        action = ActionFactory.create(plan=plan)
        user = h.make_plan_admin(plan)

        h.post_edit(client, user, action, name='New name')

        [entry] = log_entries(action)
        assert entry.action == 'wagtail.edit'
        assert entry.user == user
        assert entry.plan == plan
        assert entry.revision == action.revisions.get()

    def test_save_records_a_reversion_version(self, client, plan):
        action = ActionFactory.create(plan=plan)
        user = h.make_plan_admin(plan)

        h.post_edit(client, user, action, name='New name')

        version = Version.objects.get_for_object(action).get()
        assert version.revision.user == user
        assert version.field_dict['name'] == 'New name'

    def test_invalid_save_records_nothing(self, client, plan):
        action = ActionFactory.create(plan=plan, name='Old name')
        user = h.make_plan_admin(plan)

        response = h.post_edit(client, user, action, name='')

        assert response.status_code == 200
        assert response.context['form'].errors
        action.refresh_from_db()
        assert action.name == 'Old name'
        assert not action.revisions.exists()
        assert log_entries(action) == []

    def test_save_goes_to_the_change_log_form_when_the_plan_has_a_change_log(self, client, plan):
        enable_change_log(plan)
        action = ActionFactory.create(plan=plan)

        response = h.post_edit(client, h.make_plan_admin(plan), action, name='New name')

        revision = action.revisions.get()
        assert response['Location'] == f'{CHANGE_LOG_FORM_URL}?action={action.pk}&revision={revision.pk}'

    def test_created_action_is_live_at_once(self, client, plan):
        user = h.make_plan_admin(plan)

        response, action = create_action(client, user)

        assert response['Location'] == h.index_url()
        assert action.plan == plan
        assert action.live
        assert not action.has_unpublished_changes
        revision = action.revisions.get()
        assert revision.user == user
        assert action.live_revision == revision
        [entry] = log_entries(action)
        assert entry.action == 'wagtail.create'
        assert entry.user == user
        assert entry.revision == revision

    def test_create_goes_to_the_change_log_form_when_the_plan_has_a_change_log(self, client, plan):
        enable_change_log(plan)

        response, action = create_action(client, h.make_plan_admin(plan))

        assert response['Location'].startswith(f'{CHANGE_LOG_FORM_URL}?action={action.pk}')


class TestWithModeration:
    @pytest.mark.parametrize('make_user', [h.plan_admin_for, h.make_contact_person, h.make_moderator])
    def test_save_keeps_the_published_action_and_records_a_draft(self, client, moderated_plan, make_user):
        action = ActionFactory.create(plan=moderated_plan, name='Published name')
        user = make_user(action)

        response = h.post_edit(client, user, action, name='Draft name')

        assert response.status_code == 302
        assert response['Location'] == h.edit_url(action)
        action.refresh_from_db()
        assert action.name == 'Published name'
        assert action.has_unpublished_changes
        revision = action.revisions.get()
        assert revision.user == user
        assert revision.content['name'] == 'Draft name'
        assert action.latest_revision == revision
        assert action.live_revision is None

    def test_edit_form_shows_the_draft(self, client, moderated_plan):
        action = ActionFactory.create(plan=moderated_plan, name='Published name')
        user = h.make_contact_person(action)
        h.post_edit(client, user, action, name='Draft name')

        response = client.get(h.edit_url(action))

        assert response.context['form']['name'].value() == 'Draft name'

    def test_save_records_an_audit_log_entry(self, client, moderated_plan):
        action = ActionFactory.create(plan=moderated_plan)
        user = h.make_contact_person(action)

        h.post_edit(client, user, action, name='Draft name')

        [entry] = log_entries(action)
        assert entry.action == 'wagtail.edit'
        assert entry.user == user
        assert entry.revision == action.revisions.get()

    def test_save_does_not_go_to_the_change_log_form(self, client, moderated_plan):
        enable_change_log(moderated_plan)
        action = ActionFactory.create(plan=moderated_plan)

        response = h.post_edit(client, h.make_contact_person(action), action, name='Draft name')

        assert response['Location'] == h.edit_url(action)

    def test_invalid_save_records_nothing(self, client, moderated_plan):
        action = ActionFactory.create(plan=moderated_plan)

        response = h.post_edit(client, h.make_contact_person(action), action, name='')

        assert response.status_code == 200
        assert response.context['form'].errors
        assert not action.revisions.exists()
        assert log_entries(action) == []

    def test_created_action_is_a_draft(self, client, moderated_plan):
        user = h.make_plan_admin(moderated_plan)

        response, action = create_action(client, user)

        assert response.status_code == 302
        assert action.plan == moderated_plan
        assert action.has_unpublished_changes
        revision = action.revisions.get()
        assert revision.user == user
        assert action.latest_revision == revision
        assert action.live_revision is None
        [entry] = log_entries(action)
        assert entry.action == 'wagtail.create'
        assert entry.revision == revision


@pytest.mark.parametrize('moderated', [False, True])
def test_create_page_only_offers_saving(client, moderated):
    plan = PlanFactory.create()
    if moderated:
        h.enable_moderation(plan)
    client.force_login(h.make_plan_admin(plan))

    response = client.get(h.create_url())

    assert h.action_menu_names(response) == ['action-save', '_continue']


@pytest.mark.parametrize('moderated', [False, True])
def test_pages_do_not_autosave(client, moderated):
    plan = PlanFactory.create()
    if moderated:
        h.enable_moderation(plan)
    action = ActionFactory.create(plan=plan)
    client.force_login(h.make_plan_admin(plan))

    assert client.get(h.create_url()).context['autosave_enabled'] is False
    assert client.get(h.edit_url(action)).context['autosave_enabled'] is False


@pytest.mark.parametrize('moderated', [False, True])
def test_history_page_lists_the_saves(client, moderated):
    plan = PlanFactory.create()
    if moderated:
        h.enable_moderation(plan)
    action = ActionFactory.create(plan=plan)
    user = h.make_plan_admin(plan)
    h.post_edit(client, user, action, name='New name')

    response = client.get(h.history_url(action))

    assert response.status_code == 200
    assert b'/revert/' not in response.content


def test_core_listing_shows_the_actions_of_the_active_plan(rf, plan):
    action = ActionFactory.create(plan=plan, name='Listed action')
    other_action = ActionFactory.create(name='Action of another plan')
    user = h.make_plan_admin(plan)
    request = rf.get(h.index_url())
    request.user = user
    request.admin_cache = PlanSpecificCache(plan=plan)
    request.get_active_admin_plan = lambda: plan

    with ctx_request.activate(request):
        response = ActionViewSet().index_view(request)
        response.render()

    content = response.content.decode()
    assert action.name in content
    assert other_action.name not in content
    assert h.edit_url(action) in content


def save_button_label(response) -> str:
    html = response.content.decode()
    button = html[html.index('class="button action-save') :]
    label = button[button.index('<em') : button.index('</em>')]
    return label.split('>')[-1].strip()


@pytest.mark.parametrize(('moderated', 'edit_label'), [(False, 'Save'), (True, 'Save draft')])
def test_save_button_says_draft_only_where_saves_are_drafts(client, moderated, edit_label):
    plan = PlanFactory.create()
    if moderated:
        h.enable_moderation(plan)
    action = ActionFactory.create(plan=plan)
    client.force_login(h.make_plan_admin(plan))

    assert save_button_label(client.get(h.create_url())) == 'Save'
    assert save_button_label(client.get(h.edit_url(action))) == edit_label


@pytest.mark.parametrize('moderated', [False, True])
def test_edit_page_tracks_who_else_is_editing(client, moderated):
    plan = PlanFactory.create()
    if moderated:
        h.enable_moderation(plan)
    action = ActionFactory.create(plan=plan)
    first_user = h.make_plan_admin(plan)
    second_user = h.make_plan_admin(plan)
    h.get_edit_page(client, first_user, action)

    response = h.get_edit_page(client, second_user, action)

    sessions = EditingSession.objects.filter(object_id=str(action.pk))
    assert {session.user for session in sessions} == {first_user, second_user}
    ping_url = response.context['editing_sessions'].ping_url
    ping = client.post(ping_url)
    assert ping.status_code == 200
    assert [other['user'] for other in ping.json()['other_sessions']] == [first_user.get_full_name() or str(first_user)]
