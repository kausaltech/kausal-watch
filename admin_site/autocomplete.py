from dal import autocomplete
from django.db.models import Q
from django_orghierarchy.models import Organization


class OrganizationAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        # Don't forget to filter out results depending on the visitor !
        if not self.request.user.is_authenticated:
            return Organization.objects.none()

        user = self.request.user
        plan = user.get_active_admin_plan()
        qs = plan.get_related_organizations().filter(dissolution_date=None)

        if self.q:
            qs = qs.filter(Q(distinct_name__icontains=self.q) | Q(name__icontains=self.q))

        return qs
