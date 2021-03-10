from dal import autocomplete
from django.db.models import Q
from .models import Person


class PersonAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Person.objects.none()

        user = self.request.user
        plan = user.get_active_admin_plan()
        qs = Person.objects.available_for_plan(plan)

        if self.q:
            qs = qs.filter(Q(first_name__icontains=self.q) | Q(last_name__icontains=self.q))

        return qs
