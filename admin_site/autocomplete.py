from dal import autocomplete
from django.db.models import Q

from actions.models import Action
from aplans.types import WatchAdminRequest


class ActionAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: Action):
        related_plans = self.forwarded.get('related_plans', False)
        if related_plans:
            plan = result.plan
            plan_name = plan.short_name or plan.name
            return '%s: %s' % (plan_name, str(result))
        return str(result)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Action.objects.none()

        plan = self.request.get_active_admin_plan()
        related_plans = self.forwarded.get('related_plans', False)
        if related_plans:
            plans = plan.get_all_related_plans(inclusive=True)
        else:
            plans = [plan]
        qs = Action.objects.filter(plan__in=plans).select_related('plan')
        if self.q:
            qs = qs.filter(Q(identifier__istartswith=self.q) | Q(name__icontains=self.q) | Q(official_name__icontains=self.q))

        return qs
