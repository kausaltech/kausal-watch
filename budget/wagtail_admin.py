from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import FieldPanel, InlinePanel
from wagtail_modeladmin.options import modeladmin_register

from admin_site.wagtail import AplansModelAdmin
from budget.models import Dimension


@modeladmin_register
class DimensionAdmin(AplansModelAdmin):
    model = Dimension
    menu_order = 2100
    menu_icon = 'kausal-dimension'
    menu_label = _('Budget dimensions')
    list_display = ('name',)
    add_to_settings_menu = True

    panels = [
        FieldPanel('name'),
        InlinePanel('categories', panels=[FieldPanel('label')], heading=_('Categories')),
    ]
