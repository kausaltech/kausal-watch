from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtail.snippets.models import register_snippet
from wagtail.snippets.views.snippets import SnippetViewSet

from .models import Client


class ClientViewSet(SnippetViewSet[Client]):
    model = Client
    icon = 'globe'
    menu_order = 520
    list_display = ('name',)
    search_fields = ('name',)
    add_to_admin_menu = True

    panels = [
        FieldPanel('name'),
        FieldPanel('logo'),
        FieldPanel('auth_backend'),
        InlinePanel('email_domains', panels=[FieldPanel('domain')], heading=_('Email domains')),
        InlinePanel('plans', panels=[FieldPanel('plan')], heading=_('Plans')),
    ]


register_snippet(ClientViewSet)
