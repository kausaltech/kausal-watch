from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail import hooks
from wagtail.search.backends import get_search_backend

from generic_chooser.views import ModelChooserMixin, ModelChooserViewSet
from generic_chooser.widgets import AdminChooser

from admin_site.utils import ChooserListingTabMixinWithEmptyResultsMessage

from .models import Dimension, Indicator, IndicatorDimension


class IndicatorChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        plan = self.request.user.get_active_admin_plan()
        objs = Indicator.objects.filter(plans=plan).distinct()
        return objs

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs


class IndicatorChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = IndicatorChooserMixin

    icon = 'kausal-indicator'
    model = Indicator
    page_title = _("Choose an indicator")
    per_page = 30
    fields = ['identifier', 'name']


class IndicatorChooser(AdminChooser):
    choose_one_text = _('Choose an indicator')
    choose_another_text = _('Choose another indicator')
    model = Indicator
    choose_modal_url_name = 'indicator_chooser:choose'


@hooks.register('register_admin_viewset')
def register_indicator_chooser_viewset():
    return IndicatorChooserViewSet('indicator_chooser', url_prefix='indicator-chooser')


class DimensionChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        request = self.request
        user = request.user

        plan = user.get_active_admin_plan()
        if not plan:
            return Dimension.objects.none()

        indicator_id = request.GET.get('indicator_id')
        if indicator_id:
            try:
                indicator = Indicator.objects.get(
                    pk=indicator_id,
                    plans=plan
                )

                dimension_ids = indicator.dimensions.values_list('dimension_id', flat=True)
                return Dimension.objects.filter(id__in=dimension_ids)
            except (Indicator.DoesNotExist, ValueError):
                pass

        indicator_dimensions = IndicatorDimension.objects.filter(
            indicator__plans=plan
        ).values_list('dimension_id', flat=True).distinct()

        return Dimension.objects.filter(id__in=indicator_dimensions)

class DimensionChooser(AdminChooser):
    choose_one_text = _('Choose a dimension')
    choose_another_text = _('Choose another dimension')
    model = Dimension
    choose_modal_url_name = 'dimension_chooser:choose'


class DimensionChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = DimensionChooserMixin
    model = Dimension
    icon = 'tag'
    chooser_class = DimensionChooser
    url_prefix = 'dimension-chooser'
    listing_tab_mixin_class = ChooserListingTabMixinWithEmptyResultsMessage


@hooks.register('register_admin_viewset')
def register_dimension_chooser_viewset():
    return DimensionChooserViewSet('dimension_chooser', url_prefix='dimension-chooser')
