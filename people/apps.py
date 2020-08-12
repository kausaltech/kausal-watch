from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class PeopleConfig(AppConfig):
    name = 'people'
    verbose_name = _('People')

    def ready(self):
        from wagtail.admin.templatetags.wagtailadmin_tags import register
        from .models import avatar_url

        del register.tags['avatar_url']
        register.simple_tag(takes_context=True)(avatar_url)
