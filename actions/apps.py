import collections
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


# FIXME: Monkey patch due to wagtail-admin-list-controls using a deprecated alias in collections package
# Wagtail uses the deprecated alias -- remove after updating to 2.16
collections.Iterable = collections.abc.Iterable
collections.Mapping = collections.abc.Mapping


class ActionsConfig(AppConfig):
    name = 'actions'
    verbose_name = _('Actions')
