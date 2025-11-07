from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail.admin.viewsets.chooser import ChooserViewSet


class DimensionChooserViewSet(ChooserViewSet):
    model = 'indicators.Dimension'
    icon = 'tag'
    choose_one_text = _('Choose a dimension')
    choose_another_text = _('Choose another dimension')
    edit_item_text = _('Edit this dimension')
    form_fields = ['name']


dimension_chooser_viewset = DimensionChooserViewSet("dimension_chooser")


class IndicatorChooserViewSet(ChooserViewSet):
    model = 'indicators.Indicator'
    icon = 'kausal-indicator'
    choose_one_text = _('Choose an indicator')
    choose_another_text = _('Choose another indicator')
    edit_item_text = _('Edit this indicator')
    form_fields = ['identifier', 'name']
    per_page = 30

    # def get_base_object_list(self) -> QuerySet[Indicator]:
    #     user = user_or_bust(self.request.user)
    #     plan = user.get_active_admin_plan()
    #     return Indicator.objects.filter(plans=plan).distinct()

    # TODO: that was all wrong below
    # def get_object_list(self, search_term: str | None = None, **kwargs) -> QuerySet[Indicator]:
    #     #objs = self.get_base_object_list()
    #     objs = Indicator.objects.all()
    #     breakpoint()

    #     if search_term:
    #         search_backend = get_search_backend()
    #         print(search_backend)
    #         objs = search_backend.autocomplete(search_term, objs)

    #     return objs


indicator_chooser_viewset = IndicatorChooserViewSet("indicator_chooser")

# Create your views here.
