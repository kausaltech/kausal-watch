from django.urls import include, path
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .api import check_login_method

urlpatterns = [
    path('login/check/', check_login_method, name='admin_check_login_method'),
    path('impersonate/', include('hijack.urls')),
]

if not settings.LOGOUT_REDIRECT_URL:
    raise ImproperlyConfigured("You must configure LOGOUT_REDIRECT_URL.")
