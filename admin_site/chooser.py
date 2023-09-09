from django import forms
from django.utils.translation import gettext_lazy as _
from django.forms.models import modelform_factory

from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin, ModelChooserCreateTabMixin
from generic_chooser.widgets import AdminChooser
from wagtail import hooks

from actions.chooser import WatchModelChooserBase
from aplans.types import WatchAdminRequest
from aplans.fields import HostnameValidator

from .models import Client, EmailDomains


class ClientChooserMixin(WatchModelChooserBase):
    request: WatchAdminRequest

    def get_unfiltered_object_list(self):
        objects = Client.objects.all().order_by('name')
        return objects


class ClientForm(forms.ModelForm):
    default_email_hostname = forms.CharField(
        help_text=_(
            'What is the part after @ in the staff email address of the organization mainly responsible for the plan?'
        ),
        validators=[HostnameValidator()]
    )

    def save(self, commit=True):
        hostname = self.cleaned_data['default_email_hostname']
        result = super().save(commit=commit)
        EmailDomains.objects.create(client=self.instance, domain=hostname)
        return result

    class Meta:
        model = Client
        fields = ['name', 'auth_backend']


class ClientChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = ClientChooserMixin

    icon = 'user'
    model = Client
    page_title = _("Choose a client")
    per_page = 30
    fields = ['name', 'email_domains']
    form_class = ClientForm


class ClientChooser(AdminChooser):
    choose_one_text = _('Choose a client')
    choose_another_text = _('Choose another client')
    model = Client
    choose_modal_url_name = 'client_chooser:choose'


@hooks.register('register_admin_viewset')
def register_client_chooser_viewset():
    return ClientChooserViewSet('client_chooser', url_prefix='client-chooser')
