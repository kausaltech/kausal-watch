from __future__ import annotations

from contextvars import ContextVar
from typing import TYPE_CHECKING

from kausal_common.users import user_or_bust

from admin_site.permissions import PlanContextPermissionPolicy
from orgs.models import Organization
from people.models import Person

if TYPE_CHECKING:
    from actions.models import Plan
    from users.models import User


class PersonPermissionPolicy(PlanContextPermissionPolicy):
    """
    Decide about people with the roles of the user in the active plan.

    Users may always edit themselves. Otherwise editing and deleting a person needs the rights of
    `User.can_edit_or_delete_person_within_plan()`, and creating one needs plan admin rights.
    """

    def __init__(self):
        self._org_map: ContextVar[dict[int, Organization] | None] = ContextVar('person_policy_org_map', default=None)
        super().__init__(Person)

    def prefetch_cache(self):
        if self.plan is None:
            return
        org_qs = Organization.objects.get_queryset().available_for_plan(self.plan)
        self._org_map.set({org.id: org for org in org_qs})

    def clean_cache(self):
        self._org_map.set(None)

    def _get_plan(self, user: User) -> Plan:
        return self.plan or user.get_active_admin_plan()

    def user_has_permission(self, user, action):
        if action != 'add':
            return super().user_has_permission(user, action)
        # Only plan admins may create people, also in the person choosers. Contact persons may not, whatever their role.
        user = user_or_bust(user)
        return user.is_general_admin_for_plan(self._get_plan(user))

    def user_has_permission_for_instance(self, user, action, instance):
        if action not in ('change', 'delete'):
            return super().user_has_permission_for_instance(user, action, instance)
        if not super().user_has_permission(user, action):
            return False
        user = user_or_bust(user)
        assert isinstance(instance, Person)
        # Users can always edit themselves
        if action == 'change' and instance.user == user:
            return True
        return user.can_edit_or_delete_person_within_plan(instance, plan=self._get_plan(user), orgs=self._org_map.get())
