from admin_list_controls.actions import SubmitForm
from admin_list_controls.components import Block, Button, Columns, Icon
from admin_list_controls.filters import BooleanFilter
from admin_list_controls.views import ListControlsIndexView
from django.utils.translation import gettext as _

from admin_site.wagtail import PersistIndexViewFiltersMixin
from orgs.models import Organization

# This requires wagtail-admin-list-controls, which is discontinued. We phase it out when KW is upgraded to Wagtail 5.
# Until then, keep the old organization index view.
# If this module is imported in a new KW version, the one using Wagtail 5, things will explode.
class LegacyOrganizationIndexView(PersistIndexViewFiltersMixin, ListControlsIndexView):
    def build_list_controls(self):
        user = self.request.user
        plan = user.get_active_admin_plan()
        available_plans = Organization.objects.available_for_plan(plan)

        show_only_added_to_plan_filter = BooleanFilter(
            name='only_added_to_plan',
            label=_("Show only organizations in active plan"),
            apply_to_queryset=lambda qs, value: qs.filter(id__in=available_plans) if value else qs,
        )
        show_only_editable_filter = BooleanFilter(
            name='only_editable',
            label=_("Show only editable organizations"),
            apply_to_queryset=lambda qs, value: qs.editable_by_user(user) if value else qs,
        )
        return [
            Columns(column_count=2)(
                Block(extra_classes='own-action-filter')(show_only_added_to_plan_filter),
                Block(extra_classes='own-action-filter')(show_only_editable_filter)
            ),
            Button(action=SubmitForm())(
                Icon('icon icon-tick'),
                _("Apply filters"),
            ),
        ]
