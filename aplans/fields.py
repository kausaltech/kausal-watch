from django import forms
from django.core import validators
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import models
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


@deconstructible
class HostnameValidator(EmailValidator):
    message = _('Enter a valid hostname.')

    def __call__(self, value):
        if self.validate_domain_part(value):
            return
        raise ValidationError(self.message, code=self.code)


hostname_validator = HostnameValidator()


class HostnameFormField(forms.CharField):
    default_validators = [hostname_validator]

    def to_python(self, value):
        # Always convert to lower case
        ret = super().to_python(value)
        return ret.lower()

    def __init__(self, **kwargs):
        super().__init__(strip=True, **kwargs)


class HostnameField(models.CharField):
    default_validators = [hostname_validator]
    description = _("Fully qualified hostname (FQDN)")

    def __init__(self, *args, **kwargs):
        # max_length=254 to be compliant with RFCs 3696 and 5321
        kwargs.setdefault('max_length', 254)
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        # We do not exclude max_length if it matches default as we want to change
        # the default in future.
        return name, path, args, kwargs

    def formfield(self, **kwargs):
        # As with CharField, this will cause email validation to be performed
        # twice.
        return super().formfield(**{
            'form_class': HostnameFormField,
            **kwargs,
        })
