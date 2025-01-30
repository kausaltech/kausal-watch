from __future__ import annotations

from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtail.snippets.models import register_snippet

from admin_site.viewsets import WatchViewSet
from budget.models import Dimension


class DimensionAdmin(WatchViewSet):
    model = Dimension
    menu_order = 2100
    icon = 'kausal-dimension'
    menu_label = _('Budget dimensions')
    list_display = ('name',)
    add_to_settings_menu = True

    panels = [
        FieldPanel('name'),
        InlinePanel('categories', panels=[FieldPanel('label')], heading=_('Categories')),
    ]


register_snippet(DimensionAdmin)
