from django.urls import reverse
from wagtail.admin.menu import MenuItem

from actions.models.plan import Plan
from aplans.types import WatchAdminRequest


class PlanSpecificSingletonModelMenuItem(MenuItem):
    """Menu item for models of which there's only one instance of them per
    action plan. Since there's only one instance of the model, the user is
    directed straight to the edit view (instead of the index view).
    """
    def __init__(self, view_set, order):
        self.view_set = view_set

        super().__init__(
            label=view_set.menu_label,
            url="",  # This is set in render_component
            name=view_set.menu_name,
            icon_name=view_set.icon,
            order=order,
        )

    def get_one_to_one_field(self, plan: Plan):
        # Implement in subclass
        raise NotImplementedError()

    def render_component(self, request: WatchAdminRequest):
        # When clicking the menu item, use the edit view instead of the index view.
        link_menu_item = super().render_component(request)
        plan = request.user.get_active_admin_plan()
        field = self.get_one_to_one_field(plan)
        link_menu_item.url = reverse(self.view_set.get_url_name('edit'), kwargs={'pk': field.pk})
        return link_menu_item

    def is_shown(self, request: WatchAdminRequest):
        user = request.user
        if user.is_superuser:
            return True
        plan = user.get_active_admin_plan(required=False)
        if plan is None:
            return False
        field = self.get_one_to_one_field(plan)
        return self.view_set.permission_policy.user_has_permission_for_instance(user, 'change', field)
