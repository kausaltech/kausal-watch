from __future__ import annotations

from typing import TYPE_CHECKING, Any

from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _
from wagtail import hooks

from generic_chooser.views import ModelChooserMixin, ModelChooserViewSet
from generic_chooser.widgets import AdminChooser

from kausal_common.admin_site.choosers import ChooserViewSet
from kausal_common.users import user_or_bust

from admin_site.utils import ChooserListingTabMixinWithEmptyResultsMessage

from .models import Dimension, Indicator, IndicatorDimension, IndicatorValue

if TYPE_CHECKING:
    from wagtail.admin.views.generic.chooser import ChooseResultsView, ChooseView, ChosenView

    from .models import IndicatorQuerySet


class IndicatorChooserViewSet(ChooserViewSet[Indicator]):
    icon = 'kausal-indicator'
    model = Indicator
    choose_one_text = _('Choose an indicator')
    choose_another_text = _('Choose another indicator')

    def get_object_list(self, view: ChooseView | ChooseResultsView) -> IndicatorQuerySet:
        user = user_or_bust(view.request.user)
        plan = user.get_active_admin_plan()
        objs = Indicator.objects.qs.filter(plans=plan).visible_for_user(user).distinct()
        return objs

    def get_chosen_response_data(self, view: ChosenView, item: Indicator) -> dict[str, Any]:
        data = super(type(view), view).get_chosen_response_data(item)  # type: ignore[call-arg]
        data['uuid'] = str(item.uuid)
        return data


indicator_chooser_viewset = IndicatorChooserViewSet('indicator_chooser', url_prefix='indicator-chooser')


@hooks.register('register_admin_viewset')
def register_indicator_chooser_viewset():
    return indicator_chooser_viewset


class DimensionChooserMixin(ModelChooserMixin[Dimension, QuerySet[Dimension]]):
    def get_unfiltered_object_list(self):
        request = self.request
        user = user_or_bust(request.user)

        plan = user.get_active_admin_plan()
        if not plan:
            return Dimension.objects.none()

        indicator_id = request.GET.get('indicator_id')
        include_plan_dimensions = request.GET.get('include_plan_dimensions', 'false').lower() == 'true'
        if indicator_id:
            try:
                indicator = Indicator.objects.get(pk=indicator_id, plans=plan)

                dimension_ids = indicator.dimensions.values_list('dimension_id', flat=True)
                return Dimension.objects.filter(id__in=dimension_ids)
            except Indicator.DoesNotExist, ValueError:
                pass

        indicator_dimensions = (
            IndicatorDimension.objects.filter(indicator__plans=plan).values_list('dimension_id', flat=True).distinct()
        )

        dimensions = Dimension.objects.filter(id__in=indicator_dimensions)
        if include_plan_dimensions:
            plan_dimension_ids = plan.dimensions.values_list('dimension', flat=True)
            plan_dimensions = Dimension.objects.filter(id__in=plan_dimension_ids)
            dimensions |= plan_dimensions
        return dimensions


class DimensionChooser(AdminChooser):
    choose_one_text = _('Choose a dimension')
    choose_another_text = _('Choose another dimension')
    model = Dimension
    choose_modal_url_name = 'dimension_chooser:choose'

    def __init__(self, include_plan_dimensions=False, **kwargs):
        self.include_plan_dimensions = include_plan_dimensions
        super().__init__(**kwargs)

    def get_choose_modal_url(self):
        url = super().get_choose_modal_url()
        url = f'{url}?include_plan_dimensions={self.include_plan_dimensions}'
        return url


class DimensionChooserViewSet(ModelChooserViewSet[Dimension]):
    chooser_mixin_class = DimensionChooserMixin
    model = Dimension
    icon = 'tag'
    chooser_class = DimensionChooser
    url_prefix = 'dimension-chooser'
    listing_tab_mixin_class = ChooserListingTabMixinWithEmptyResultsMessage


@hooks.register('register_admin_viewset')
def register_dimension_chooser_viewset():
    return DimensionChooserViewSet('dimension_chooser', url_prefix='dimension-chooser')


class IndicatorValueChooserMixin(ModelChooserMixin[IndicatorValue, QuerySet[IndicatorValue]]):
    def get_object_string(self, item: IndicatorValue) -> str:
        return item.format_date()

    def get_unfiltered_object_list(self):
        request = self.request
        user = user_or_bust(request.user)

        plan = user.get_active_admin_plan()
        indicator_id = request.GET.get('indicator_id')
        if not indicator_id:
            return IndicatorValue.objects.none()
        try:
            indicator = Indicator.objects.get_queryset().visible_for_user(user).get(pk=indicator_id, plans=plan)
            return indicator.values.all()
        except Indicator.DoesNotExist, ValueError:
            pass

        return IndicatorValue.objects.none()


class IndicatorValueChooser(AdminChooser):
    choose_one_text = _('Choose a value')
    choose_another_text = _('Choose another value')
    model = IndicatorValue
    choose_modal_url_name = 'indicator_value_chooser:choose'
    show_create_link = False

    def __init__(self, indicator_id: int, **kwargs):
        self.indicator_id = indicator_id
        super().__init__(**kwargs)

    def get_choose_modal_url(self):
        url = super().get_choose_modal_url()
        url = f'{url}?indicator_id={self.indicator_id}'
        return url


class IndicatorValueChooserViewSet(ModelChooserViewSet[IndicatorValue]):
    chooser_mixin_class = IndicatorValueChooserMixin
    model = IndicatorValue
    icon = 'table'
    chooser_class = IndicatorValueChooser
    url_prefix = 'indicator-value-chooser'
    listing_tab_mixin_class = ChooserListingTabMixinWithEmptyResultsMessage


@hooks.register('register_admin_viewset')
def register_indicator_value_chooser_viewset():
    return IndicatorValueChooserViewSet('indicator_value_chooser', url_prefix='indicator-value-chooser')
