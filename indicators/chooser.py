from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin
from generic_chooser.widgets import AdminChooser
from django.utils.translation import gettext_lazy as _
from wagtail.search.backends import get_search_backend
from wagtail import hooks

from .models import Indicator


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

    icon = 'user'
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
