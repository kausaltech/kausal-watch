from typing import TYPE_CHECKING

from dal import autocomplete

from indicators.models import CommonIndicator, Indicator, Quantity, Unit
from orgs.models import Organization

if TYPE_CHECKING:
    from aplans.types import WatchAdminRequest

COMMON_METRIC_UNITS = [
    'tCO2e', 'ktCO2e', 'tCO2', 'kg', 'g', 't',
    'MWh', 'kWh', 'GWh', 'GJ', 'TJ',
    'EUR', 'USD', 'km', 'm', 'l', 'm³',
    'tCO2e/a', 'kg/a', 'MWh/a',
]


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

    Default (no query): curated list + numerators extracted from existing DB values.
    On search: also includes matching units from the pint registry.
    """

    def _get_curated_units(self) -> set[str]:
        from kausal_common.datasets.models import DatasetMetricComputation
        # Only look at metrics used as factors (operand_b in null-operand computations)
        factor_units = set(
            DatasetMetricComputation.objects.filter(operand_a__isnull=True)
            .exclude(operand_b__unit='').exclude(operand_b__unit__isnull=True)
            .values_list('operand_b__unit', flat=True).distinct()
        )
        # For compound units (e.g. "tCO2e/mi", "TWh/a/mi"), extract the numerator
        # by stripping the last "/{denominator}" segment (the auto-appended indicator unit).
        numerators = set()
        for u in factor_units:
            if '/' in u:
                numerators.add(u.rsplit('/', maxsplit=1)[0])
            else:
                numerators.add(u)
        return numerators | set(COMMON_METRIC_UNITS)

    @staticmethod
    def _search_pint_units(query: str) -> list[str]:
        """Search the pint registry for units matching the query."""
        from aplans.dataset_config import _get_unit_registry
        ureg = _get_unit_registry()
        q = query.lower()
        matches: set[str] = set()
        # Search base unit names (includes our custom tCO2e, ktCO2e, EUR, etc.)
        for name in ureg._units:
            if q in name.lower():
                matches.add(name)
        # Also try parsing the query directly — handles prefixed units like TWh
        try:
            parsed = ureg.parse_expression(query)
            unit_str = str(parsed.units)
            # Add both the user's input and the canonical form
            matches.add(query)
            if unit_str != query:
                matches.add(unit_str)
        except Exception:  # noqa: S110
            pass  # Invalid unit expression, skip
        return sorted(matches)

    def get_list(self):
        return sorted(self._get_curated_units())

    def autocomplete_results(self, results):
        """On search, extend curated results with matching pint units."""
        q = self.q.lower()
        curated = {x for x in results if q in x.lower()}
        pint_matches = set(self._search_pint_units(self.q))
        return sorted(curated | pint_matches)

    def create(self, text):
        return text
