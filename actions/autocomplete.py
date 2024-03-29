from dal import autocomplete
from django.db.models import Q

from actions.models import Action, Category, CommonCategoryType, Plan
from aplans.types import WatchAdminRequest


class ActionAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: Action):
        related_plans = self.forwarded.get('related_plans', False)
        plan_id = self.forwarded.get('plan', None)
        if related_plans or plan_id is not None:
            plan = result.plan
            plan_name = plan.short_name or plan.name
            return '%s: %s' % (plan_name, str(result))
        return str(result)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Action.objects.none()

        plan_id = self.forwarded.get('plan', None)
        if plan_id is None:
            plan = self.request.get_active_admin_plan()
        else:
            plan = Plan.objects.get(id=plan_id)
        related_plans = self.forwarded.get('related_plans', False)
        if related_plans:
            plans = plan.get_all_related_plans(inclusive=True)
        else:
            plans = [plan]
        qs = Action.objects.filter(plan__in=plans).select_related('plan')
        if self.q:
            qs = qs.filter(Q(identifier__istartswith=self.q) | Q(name__icontains=self.q) | Q(official_name__icontains=self.q))

        return qs


class CategoryAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: Category):
        return str(result)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Category.objects.none()

        plan = self.request.get_active_admin_plan()
        ct_id = self.forwarded.get('type', None)
        target_type = self.forwarded.get('target_type', None)

        if ct_id is None and target_type is None:
            return Category.objects.none()

        category_types = plan.category_types.all()
        if target_type in ('indicator', 'action'):
            for restriction in ('usable', 'editable'):
                category_types = category_types.filter(**{f'{restriction}_for_{target_type}s': True})
        if ct_id:
            category_types = category_types.filter(id=ct_id)

        categories = Category.objects.filter(type__in=category_types)
        if self.q:
            q = self.q.strip()
            categories = categories.filter(
                Q(identifier__istartswith=q) |
                Q(name__icontains=q)
            )
        return categories


class CommonCategoryTypeAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: CommonCategoryType):
        return str(result)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return CommonCategoryType.objects.none()

        return CommonCategoryType.objects.all()
