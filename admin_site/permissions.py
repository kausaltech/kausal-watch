from typing import Optional
from django.conf import settings
from wagtail.permission_policies.collections import CollectionOwnershipPermissionPolicy

from aplans.types import WatchAdminRequest


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
