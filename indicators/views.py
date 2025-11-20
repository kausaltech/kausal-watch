from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail.admin.views.generic.chooser import ChooseResultsView, ChooseView
from wagtail.admin.viewsets.chooser import ChooserViewSet

from kausal_common.users import user_or_bust


class DimensionChooseView(ChooseView):
    def get_object_list(self):
        """Filter dimensions based on plan and context (detect indicator from referer)."""
        from indicators.models import Dimension, Indicator, IndicatorDimension

        request = self.request
        user = user_or_bust(request.user)

        plan = user.get_active_admin_plan()
        if not plan:
            return Dimension.objects.none()
        indicator_id = request.GET.get('indicator')
        include_plan_dimensions = request.GET.get('include_plan_dimensions', 'false').lower() == 'true'

        if indicator_id:
            try:
                indicator = Indicator.objects.get(pk=indicator_id, plans=plan)
                dimension_ids = indicator.dimensions.values_list('dimension_id', flat=True)
                return Dimension.objects.filter(id__in=dimension_ids)
            except (Indicator.DoesNotExist, ValueError):
                pass

        indicator_dimensions = IndicatorDimension.objects.filter(
            indicator__plans=plan).values_list('dimension_id', flat=True).distinct()

        dimensions = Dimension.objects.filter(id__in=indicator_dimensions)
        if include_plan_dimensions:
            plan_dimension_ids = plan.dimensions.values_list('dimension', flat=True)
            plan_dimensions = Dimension.objects.filter(id__in=plan_dimension_ids)
            dimensions |= plan_dimensions
        return dimensions


class DimensionChooserViewSet(ChooserViewSet):
    model = 'indicators.Dimension'
    icon = 'tag'
    choose_one_text = _('Choose a dimension')
    choose_another_text = _('Choose another dimension')
    edit_item_text = _('Edit this dimension')
    form_fields = ['name']
    choose_view_class = DimensionChooseView
    preserve_url_parameters = ["indicator", "include_plan_dimensions"]

    @property
    def widget_class(self):
        class DimensionWidget(super().widget_class): # type: ignore
            def __init__(self, include_plan_dimensions=False, **kwargs):
                super().__init__(**kwargs)
                self.include_plan_dimensions = include_plan_dimensions

            def get_chooser_modal_url(self) -> str:
                url = super().get_chooser_modal_url()
                if self.include_plan_dimensions:
                    separator = '&' if '?' in url else '?'
                    url = f"{url}{separator}include_plan_dimensions=true"
                return url

        return DimensionWidget

dimension_chooser_viewset = DimensionChooserViewSet("dimension-chooser")


class IndicatorChooseResultsView(ChooseResultsView):
    def get_object_list(self):
        objects = super().get_object_list()
        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()

        return objects.filter(plans=plan).distinct()


class IndicatorChooseView(ChooseView):
    def get_object_list(self):
        """Filter indicators by the current user's active plan."""
        from indicators.models import Indicator

        user = user_or_bust(self.request.user)
        plan = user.get_active_admin_plan()
        return Indicator.objects.filter(plans=plan).distinct()


class IndicatorChooserViewSet(ChooserViewSet):
    model = 'indicators.Indicator'
    icon = 'kausal-indicator'
    choose_one_text = _('Choose an indicator')
    choose_another_text = _('Choose another indicator')
    edit_item_text = _('Edit this indicator')
    form_fields = ['identifier', 'name']
    per_page = 30
    choose_view_class = IndicatorChooseView
    choose_results_view_class = IndicatorChooseResultsView


indicator_chooser_viewset = IndicatorChooserViewSet("indicator-chooser")

# Create your views here.
