from wagtail.core.permission_policies.collections import CollectionOwnershipPermissionPolicy


class PlanRelatedCollectionOwnershipPermissionPolicy(CollectionOwnershipPermissionPolicy):
    def collections_user_has_any_permission_for(self, user, actions):
        qs = super().collections_user_has_any_permission_for(user, actions)
        plan = user.get_active_admin_plan()
        qs = qs.descendant_of(plan.root_collection, inclusive=True)
        return qs

    def instances_user_has_any_permission_for(self, user, actions):
        qs = super().instances_user_has_any_permission_for(user, actions)
        plan = user.get_active_admin_plan()
        collections = plan.root_collection.get_descendants(inclusive=True)
        qs = qs.filter(collection__in=collections)
        return qs
