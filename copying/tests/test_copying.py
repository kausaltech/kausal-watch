from __future__ import annotations

import pytest

from actions.tests.factories import ActionContactFactory, WorkflowFactory
from copying.main import copy_plan

pytestmark = pytest.mark.django_db


def test_publish_copied_action_does_not_steal_contact_persons(plan_with_pages, action, user):
    ActionContactFactory(action=action)
    plan = plan_with_pages
    plan.features.moderation_workflow = WorkflowFactory()
    plan.features.save(update_fields=['moderation_workflow'])
    action.save_revision(user=user)
    plan_copy = copy_plan(plan)
    assert action == plan.actions.first()
    action_copy = plan_copy.actions.first()
    assert action_copy
    assert action_copy.latest_revision
    action_copy.latest_revision.publish()
    assert action.contact_persons.exists()
