from django.utils.translation import gettext_lazy as _

from generic_chooser.views import ModelChooserViewSet
from generic_chooser.widgets import AdminChooser
from wagtail import hooks

from actions.chooser import WatchModelChooserBase
from aplans.types import WatchAdminRequest

from .models import Organization


class OrganizationChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        objects = Organization.objects.filter(depth=1)
        return objects


class OrganizationChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = OrganizationChooserMixin

    icon = 'user'
    model = Organization
    page_title = _("Choose an organization")
    per_page = 30
    fields = ['name']


class OrganizationChooser(AdminChooser):
    choose_one_text = _('Choose an organization')
    choose_another_text = _('Choose another organization')
    model = Organization
    choose_modal_url_name = 'organization_chooser:choose'


@hooks.register('register_admin_viewset')
def register_organization_chooser_viewset():
    return OrganizationChooserViewSet('organization_chooser', url_prefix='organization-chooser')
