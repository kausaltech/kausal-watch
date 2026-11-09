from __future__ import annotations

from contextvars import copy_context

import pytest

from actions.tests.factories import PlanFactory
from people.permission_policy import PersonPermissionPolicy
from people.tests.factories import PersonFactory
from users.tests.factories import UserFactory

pytestmark = pytest.mark.django_db


def test_plan_context_is_not_shared_between_concurrent_requests():
    plan_a, plan_b = PlanFactory.create(), PlanFactory.create()
    admin = UserFactory.create()
    PersonFactory.create(user=admin, general_admin_plans=[plan_a])
    person = PersonFactory.create(organization=plan_a.organization)
    policy = PersonPermissionPolicy()
    request_a, request_b = copy_context(), copy_context()

    context_a = policy.activate_plan_context(plan_a)
    context_b = policy.activate_plan_context(plan_b)
    request_a.run(context_a.__enter__)
    request_b.run(context_b.__enter__)
    try:
        assert request_a.run(policy.user_has_permission_for_instance, admin, 'change', person)
        assert request_b.run(lambda: policy.plan) == plan_b
    finally:
        request_b.run(context_b.__exit__, None, None, None)
        request_a.run(context_a.__exit__, None, None, None)
    assert policy.plan is None
