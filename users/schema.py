from enum import Enum
from typing import cast

import strawberry as sb

from kausal_common.users.schema import UserNode

from aplans import gql

from actions.models import Action, ActionContactPerson, Plan
from orgs.models import Organization
from people.models import Person
from users.models import User


@sb.enum
class TestUserRoleKind(Enum):
    PLAN_ADMIN = 'plan_admin'
    ACTION_CONTACT = 'action_contact'


@sb.input
class TestUserRoleInput:
    kind: TestUserRoleKind
    target_id: sb.ID


@sb.input
class TestUserInput:
    email: str
    password: str
    is_superuser: bool = False
    default_admin_plan_id: sb.ID | None = None
    roles: list[TestUserRoleInput] = sb.field(default_factory=list)


@sb.type
class TestMode:
    @gql.mutation
    def create_test_user(self, info: gql.Info, input: TestUserInput) -> UserNode:
        user = User(email=input.email, is_superuser=input.is_superuser)
        user.set_password(input.password)
        user.is_active = True
        user.deactivated_by = None
        user.clean()
        user.full_clean()
        user.save()
        org = Organization.objects.filter(name='Test Organization').first()
        if org is None:
            org = Organization.add_root(name='Test Organization')
        person = Person.objects.create(first_name='Test', last_name='User', email=user.email, user=user, organization=org)

        active_plan: Plan | None = None
        if input.default_admin_plan_id:
            active_plan = Plan.objects.qs.by_id_or_identifier(input.default_admin_plan_id).get()

        for role in input.roles:
            if role.kind == TestUserRoleKind.PLAN_ADMIN:
                plan = Plan.objects.qs.by_id_or_identifier(role.target_id).get()
                plan.general_admins.add(person)
                plan.save()
                if active_plan is None:
                    active_plan = plan
            elif role.kind == TestUserRoleKind.ACTION_CONTACT:
                action = Action.objects.qs.get(id=role.target_id)
                acp = ActionContactPerson.objects.create(person=person, action=action)
                action.contact_persons.add(acp)
                action.save()
                if active_plan is None:
                    active_plan = action.plan

        if active_plan:
            user.selected_admin_plan = active_plan
            user.save()

        return cast('UserNode', user)  # pyright: ignore[reportInvalidCast]
