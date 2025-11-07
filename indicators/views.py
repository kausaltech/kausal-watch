from __future__ import annotations

from django.shortcuts import render
from django.utils.translation import gettext_lazy as _
from wagtail.admin.viewsets.chooser import ChooserViewSet


class DimensionChooserViewSet(ChooserViewSet):
    model = 'indicators.Dimension'
    icon = 'tag'
    choose_one_text = _('Choose a dimension')
    choose_another_text = _('Choose another dimension')
    edit_item_text = _('Edit this dimension')
    form_fields = ['name']


dimension_chooser_viewset = DimensionChooserViewSet("dimension_chooser")

# Create your views here.
