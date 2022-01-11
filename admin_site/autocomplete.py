from dal import autocomplete
from django.db.models import Q

from actions.models import Action


class ActionAutocomplete(autocomplete.Select2QuerySetView):
    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Action.objects.none()

        user = self.request.user
        plan = user.get_active_admin_plan()
        qs = Action.objects.filter(plan=plan)

        if self.q:
            qs = qs.filter(Q(identifier__istartswith=self.q) | Q(name__icontains=self.q) | Q(official_name__icontains=self.q))

        return qs
