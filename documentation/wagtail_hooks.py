from django.urls import re_path

from wagtail import hooks

from . import views


@hooks.register('register_admin_urls')
def register_admin_urls():
    return [
        re_path(r'^documentation/(?P<page_id>[-\w]+)/$', views.index, name='documentation')
    ]
