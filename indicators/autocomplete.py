from dal import autocomplete

from indicators.models import Unit, Quantity
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
