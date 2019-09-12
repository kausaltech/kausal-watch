from django.contrib.admin.apps import AdminConfig
from django.apps import AppConfig


class AdminSiteConfig(AdminConfig):
    default_site = 'admin_site.admin.AplansAdminSite'


class AdminSiteStatic(AppConfig):
    name = 'admin_site'
