from django.utils.translation import gettext_lazy as _
from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin
from generic_chooser.widgets import AdminChooser
from wagtail.search.backends import get_search_backend
from wagtail import hooks

from .models import ReportType
from aplans.types import WatchAdminRequest


class ReportTypeChooserMixin(ModelChooserMixin):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        plan = self.request.get_active_admin_plan()
        return ReportType.objects.filter(plan=plan)

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs

    def user_can_create(self, user):
        # Don't let users create report types in the chooser
        return False


class ReportTypeChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = ReportTypeChooserMixin

    icon = 'folder-open-inverse'
    model = ReportType
    page_title = _("Choose a report type")
    per_page = 30
    fields = ['name']


class ReportTypeChooser(AdminChooser):
    choose_one_text = _('Choose a report type')
    choose_another_text = _('Choose another report type')
    model = ReportType
    choose_modal_url_name = 'report_type_chooser:choose'


@hooks.register('register_admin_viewset')
def register_report_type_chooser_viewset():
    return ReportTypeChooserViewSet('report_type_chooser', url_prefix='report-type-chooser')
