from dal import autocomplete
from django.db.models import Q

from orgs.models import Organization
from aplans.types import WatchAdminRequest


class OrganizationAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: Organization):
        return result.get_fully_qualified_name()

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Organization.objects.none()

        user = self.request.user
        plan = user.get_active_admin_plan()
        qs = plan.get_related_organizations().filter(dissolution_date=None)

        responsible = self.forwarded.get('responsible_for_actions')
        if responsible:
            qs = qs.filter(responsible_actions__action__plan=plan).distinct()

        if self.q:
            qs = qs.filter(
                Q(distinct_name__icontains=self.q) |
                Q(name__icontains=self.q) |
                Q(internal_abbreviation__icontains=self.q) |
                Q(abbreviation__icontains=self.q)
            )

        return qs
