from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail.models import ModelLogEntry

import pytest

from actions.models.action import ActionChangeLogMessage
from actions.tests.factories import ActionFactory, PlanFactory
from actions.tests.test_change_log_graphql import make_plan_admin
from audit_logging.models import PlanScopedModelLogEntry

if TYPE_CHECKING:
    from actions.models import Action
    from users.models import User

pytestmark = pytest.mark.django_db


@pytest.fixture
def action() -> Action:
    return ActionFactory.create(plan=PlanFactory.create())


@pytest.fixture
def admin_user(action: Action) -> User:
    return make_plan_admin(action.plan)


def test_entries_visible_after_other_log_models_were_asked(admin_user: User, action: Action):
    message = ActionChangeLogMessage.objects.create(action=action, plan=action.plan, content='Text')
    PlanScopedModelLogEntry.objects.log_action(message, 'wagtail.create', user=admin_user)
    # Wagtail caches the visible content types on the user, computed from the log model asked first
    list(ModelLogEntry.objects.viewable_by_user(admin_user))

    assert PlanScopedModelLogEntry.objects.viewable_by_user(admin_user).count() == 1
