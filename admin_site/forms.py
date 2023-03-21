from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy
from django import forms

from .models import Client, AdminHostname


class LoginForm(AuthenticationForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'placeholder': gettext_lazy("Enter password"),
        }))

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request=request, *args, **kwargs)
        email_attrs = self.fields['username'].widget.attrs
        email_attrs['placeholder'] = gettext_lazy("Enter your email address")
        email_attrs['autofocus'] = True
        self.clients = Client.objects.for_request(request) if request is not None else None
        self.hide_login_form = self.clients.filter(azure_ad_tenant_id__isnull=False).exists()

        admin_hostname = AdminHostname.objects.get_for_request(request)
        self.header_text = admin_hostname.login_header_text

    @property
    def extra_fields(self):
        for field_name, field in self.fields.items():
            if field_name not in ['username', 'password']:
                yield field_name, field
