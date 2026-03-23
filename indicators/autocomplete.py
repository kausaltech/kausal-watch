from typing import TYPE_CHECKING

from dal import autocomplete

from indicators.models import CommonIndicator, Indicator, Quantity, Unit
from orgs.models import Organization

if TYPE_CHECKING:
    from aplans.types import WatchAdminRequest


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


class MetricUnitAutocomplete(autocomplete.Select2ListView):
    """
    Autocomplete for the factor unit numerator.

    Shows existing indicator unit short names plus numerators extracted from
    existing factor values in the DB. Free-text entry is allowed.
    """

    def _get_indicator_units(self) -> set[str]:
        """Return short_name (or name as fallback) from all indicator Units."""
        units: set[str] = set()
        for short_name, name in Unit.objects.values_list('short_name', 'name'):
            units.add(short_name or name)
        return units

    def get_list(self):
        return sorted(self._get_indicator_units())

    def autocomplete_results(self, results):
        q = self.q.lower()
        return sorted(x for x in results if q in x.lower())

    def create(self, text):
        return text
