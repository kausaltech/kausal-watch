from dal import autocomplete

from aplans.types import WatchAdminRequest
from indicators.models import CommonIndicator, Indicator, Quantity, Unit
from orgs.models import Organization


class BaseAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result):
        return result.autocomplete_label()

    def get_queryset(self):
        Model = self.model
        if not self.request.user.is_authenticated:
            return Model.objects.none()
        return Model.objects.filter(name_i18n__icontains=self.q)


class QuantityAutocomplete(BaseAutocomplete):
    model = Quantity


class UnitAutocomplete(BaseAutocomplete):
    model = Unit


class CommonIndicatorAutocomplete(BaseAutocomplete):
    model = CommonIndicator


class IndicatorAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result):
        return result.autocomplete_label()

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Indicator.objects.none()
        qs = Indicator.objects.all()
        plan = self.request.user.get_active_admin_plan()
        if self.request.user.is_superuser:
            qs = qs.filter(organization__in=Organization.objects.available_for_plan(plan))
        else:
            qs = qs.filter(organization=plan.organization)
        return qs.filter(name_i18n__icontains=self.q)
