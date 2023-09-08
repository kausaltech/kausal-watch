from django import forms

from django.utils.translation import gettext_lazy as _

from generic_chooser.views import ModelChooserMixin, ModelChooserViewSet
from generic_chooser.widgets import AdminChooser
from wagtail import hooks

from aplans.types import WatchAdminRequest

from .models import Organization


class OrganizationChooserMixin(ModelChooserMixin):
    """This chooser is currently intended only for choosing (and creating) top level organizations
    by superusers creating new plans. That's why it only supports root level organizations
    at the moment.
    """

    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        return Organization.get_root_nodes()

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            objs = objs.filter(name__icontains=search_term)

        return objs


class OrgForm(forms.ModelForm):
    def save(self, commit=True):
        Organization.add_root(instance=self.instance)
        return self.instance

    class Meta:
        model = Organization
        fields = ['name']


class OrganizationChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = OrganizationChooserMixin

    icon = 'user'
    model = Organization
    page_title = _("Choose an organization")
    per_page = 30
    fields = ['name']
    form_class = OrgForm


class OrganizationChooser(AdminChooser):
    choose_one_text = _('Choose an organization')
    choose_another_text = _('Choose another organization')
    model = Organization
    choose_modal_url_name = 'organization_chooser:choose'


@hooks.register('register_admin_viewset')
def register_organization_chooser_viewset():
    return OrganizationChooserViewSet('organization_chooser', url_prefix='organization-chooser')
