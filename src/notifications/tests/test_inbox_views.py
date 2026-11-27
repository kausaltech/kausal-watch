from __future__ import annotations

from typing import TYPE_CHECKING

from django.urls import reverse

import pytest

from actions.tests import action_admin_helpers as h
from actions.tests.factories import ActionFactory, PlanFactory
from notifications.inbox import notify
from notifications.inbox_views import UNREAD_COUNT_CAP
from notifications.models import InboxNotification

if TYPE_CHECKING:
    from actions.models import Action
    from users.models import User

pytestmark = pytest.mark.django_db

Type = InboxNotification.Type


@pytest.fixture(autouse=True)
def moderation_ui(settings):
    settings.ENABLE_ACTION_MODERATION_UI = True


@pytest.fixture
def action() -> Action:
    return ActionFactory.create(plan=PlanFactory.create())


@pytest.fixture
def moderator(action) -> User:
    return h.make_moderator(action)


@pytest.fixture
def editor(action) -> User:
    return h.make_contact_person(action)


def notify_moderator(action: Action, moderator: User, editor: User, **kwargs) -> InboxNotification:
    [notification] = notify([moderator], Type.ACTION_SUBMITTED, action, plan=action.plan, actor=editor, **kwargs)
    return notification


def test_unread_count(client, action, moderator, editor):
    notify_moderator(action, moderator, editor)
    client.force_login(moderator)

    data = client.get(reverse('notifications_inbox_unread_count')).json()

    assert data == {'count': 1, 'capped': False, 'label': '1 unread notification'}


def test_unread_count_is_capped(client, action, moderator, editor):
    for _ in range(UNREAD_COUNT_CAP + 1):
        notify_moderator(action, moderator, editor)
    client.force_login(moderator)

    data = client.get(reverse('notifications_inbox_unread_count')).json()

    assert data['count'] == UNREAD_COUNT_CAP
    assert data['capped'] is True


def test_inbox_lists_only_own_notifications(client, action, moderator, editor):
    notify_moderator(action, moderator, editor, comment='Have a look')
    notify([editor], Type.ACTION_APPROVED, action, plan=action.plan, actor=moderator)
    client.force_login(moderator)

    response = client.get(reverse('notifications_inbox'))

    assert response.status_code == 200
    assert [n.type for n, _ in response.context['rows']] == [Type.ACTION_SUBMITTED]
    content = response.content.decode()
    assert f'The action &quot;{action}&quot; is waiting for your review.' in content
    assert 'Have a look' in content


def test_opening_marks_read_and_redirects_to_the_action(client, action, moderator, editor):
    notification = notify_moderator(action, moderator, editor)
    client.force_login(moderator)

    response = client.get(reverse('notifications_inbox_open', args=[notification.pk]))

    assert response.status_code == 302
    assert response.url == h.edit_url(action)
    notification.refresh_from_db()
    assert notification.read_at is not None


def test_opening_a_deleted_object_says_it_is_gone(client, action, moderator, editor):
    other_action = ActionFactory.create(plan=action.plan)
    notification = notify_moderator(other_action, moderator, editor)
    title = str(other_action)
    other_action.delete()
    client.force_login(moderator)

    response = client.get(reverse('notifications_inbox_open', args=[notification.pk]), follow=True)

    assert response.redirect_chain[-1][0] == reverse('notifications_inbox')
    assert h.message_texts(response) == [f'"{title}" is no longer available.']


def test_cannot_open_someone_elses_notification(client, action, moderator, editor):
    notification = notify_moderator(action, moderator, editor)
    client.force_login(editor)

    response = client.get(reverse('notifications_inbox_open', args=[notification.pk]))

    assert response.status_code == 404


def test_mark_all_read(client, action, moderator, editor):
    notify_moderator(action, moderator, editor)
    notify_moderator(action, moderator, editor)
    client.force_login(moderator)

    client.post(reverse('notifications_inbox_mark_all_read'))

    assert not InboxNotification.objects.filter(recipient=moderator).unread().exists()


def test_front_page_and_sidebar_show_unread(client, action, moderator, editor):
    notify_moderator(action, moderator, editor)
    client.force_login(moderator)

    content = client.get(reverse('wagtailadmin_home')).content.decode()

    assert '1 unread notification.' in content
    assert 'data-inbox-unread' in content


def test_nothing_shown_without_unread(client, action, moderator):
    client.force_login(moderator)

    content = client.get(reverse('wagtailadmin_home')).content.decode()

    assert 'unread-notifications-panel' not in content
    assert 'data-inbox-unread' not in content
    assert 'data-inbox-link' in content


def test_inbox_is_off_without_the_moderation_ui(client, settings, moderator):
    settings.ENABLE_ACTION_MODERATION_UI = False
    client.force_login(moderator)

    assert client.get(reverse('notifications_inbox')).status_code == 404
    assert client.get(reverse('notifications_inbox_unread_count')).status_code == 404
    assert 'data-inbox-link' not in client.get(reverse('wagtailadmin_home')).content.decode()
