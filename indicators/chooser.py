from __future__ import annotations

from django.db.models.query import QuerySet
from django.utils.translation import gettext_lazy as _
from wagtail import hooks

from generic_chooser.views import ModelChooserMixin, ModelChooserViewSet
from generic_chooser.widgets import AdminChooser

from kausal_common.users import user_or_bust

from admin_site.utils import ChooserListingTabMixinWithEmptyResultsMessage

from .models import Indicator, IndicatorValue


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
            indicator = Indicator.objects.get_queryset().visible_for_user(user).get(
                pk=indicator_id,
                plans=plan
            )
            return indicator.values.all()
        except (Indicator.DoesNotExist, ValueError):
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
        url = f"{url}?indicator_id={self.indicator_id}"
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
