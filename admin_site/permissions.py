from contextlib import contextmanager
from typing import Optional

from django.conf import settings
from wagtail.permission_policies.base import ModelPermissionPolicy
from wagtail.permission_policies.collections import (
    CollectionOwnershipPermissionPolicy
)

from actions.models.plan import Plan
from aplans.types import WatchAdminRequest
from aplans.utils import PlanRelatedModel


class PlanRelatedCollectionOwnershipPermissionPolicy(CollectionOwnershipPermissionPolicy):
    def collections_user_has_any_permission_for(self, user, actions, request: Optional[WatchAdminRequest] = None):
        qs = super().collections_user_has_any_permission_for(user, actions)
        if request is not None:
            plan = request.get_active_admin_plan()
        else:
            plan = user.get_active_admin_plan()
        qs = qs.descendant_of(plan.root_collection, inclusive=True)
        if user.is_superuser:
            common_cat_coll = qs.model.objects.filter(name=settings.COMMON_CATEGORIES_COLLECTION).first()
            if common_cat_coll is not None:
                qs |= common_cat_coll.get_descendants(inclusive=True)
        return qs

    def instances_user_has_any_permission_for(self, user, actions):
        qs = super().instances_user_has_any_permission_for(user, actions)
        plan = user.get_active_admin_plan()
        collections = plan.root_collection.get_descendants(inclusive=True)
        qs = qs.filter(collection__in=collections)
        return qs


class PlanSpecificSingletonModelSuperuserPermissionPolicy(ModelPermissionPolicy):
    """Allow access to edit a plan specific singleton model only if user is superuser."""

    def user_has_permission(self, user, action):
        if action == 'change' and user.is_superuser:
            return True
        return False


class PlanContextPermissionPolicy(ModelPermissionPolicy):
    plan: Plan | None

    def __init__(self, model, inspect_view_enabled=False):
        self.plan = None
        super().__init__(model, inspect_view_enabled)

    def prefetch_cache(self):
        """Prefetch plan-related content for permission checking."""
        pass

    def clean_cache(self):
        pass

    @contextmanager
    def activate_plan_context(self, plan: Plan):
        self.plan = plan
        self.prefetch_cache()
        try:
            yield
        finally:
            self.clean_cache()
            self.plan = None


class PlanRelatedPermissionPolicy(ModelPermissionPolicy):
    check_admin_plan = True

    def disable_admin_plan_check(self):
        self.check_admin_plan = False

    def get_plans(self, obj):
        if isinstance(obj, PlanRelatedModel):
            return obj.get_plans()
        else:
            raise NotImplementedError('implement in subclass')

    def _obj_matches_active_plan(self, user, obj):
        if not self.check_admin_plan:
            return True

        obj_plans = self.get_plans(obj)
        active_plan = user.get_active_admin_plan()
        for obj_plan in obj_plans:
            if obj_plan == active_plan:
                return True
        return False

    def user_has_permission_for_instance(self, user, action, instance):
        if not super().user_has_permission_for_instance(user, action, instance):
            return False
        return self._obj_matches_active_plan(user, instance)


def superusers_only_hijack(*, hijacker, hijacked):
    """Only superusers may hijack other users."""
    return hijacked.is_active and hijacker.is_superuser and not hijacker.is_hijacked and hijacker != hijacked
