from __future__ import annotations

from django.urls import reverse

import pytest

from actions.action_admin import ActionAdmin
from actions.models import Action
from actions.tests.factories import ActionFactory

pytestmark = pytest.mark.django_db


def _edit_url(action: Action) -> str:
    return reverse(ActionAdmin().get_url_name('edit'), args=[action.pk])


def _login_with_plan(client, superuser, plan) -> None:
    superuser.selected_admin_plan = plan
    superuser.save(update_fields=['selected_admin_plan'])
    client.force_login(superuser)


def test_admin_edit_loads_with_bare_void_tag(client, superuser, plan) -> None:
    _login_with_plan(client, superuser, plan)
    action = ActionFactory.create(plan=plan)
    # Inject editor-incompatible markup straight into the column, bypassing the write guard.
    Action.objects.filter(pk=action.pk).update(description='<p>a<br>b</p>')
    response = client.get(_edit_url(action))
    assert response.status_code == 200


def test_admin_edit_loads_with_irreparable_markup(client, superuser, plan) -> None:
    _login_with_plan(client, superuser, plan)
    action = ActionFactory.create(plan=plan)
    Action.objects.filter(pk=action.pk).update(description='<p><em>crossed</p></em>')
    response = client.get(_edit_url(action))
    assert response.status_code == 200
