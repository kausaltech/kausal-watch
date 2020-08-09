from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from admin_site.wagtail import AdminOnlyPanel, AplansModelAdmin, AplansTabbedInterface

from .models import Indicator


class IndicatorAdmin(AplansModelAdmin):
    model = Indicator
    menu_icon = 'fa-bar-chart'  # change as required
    menu_order = 300  # will put in 3rd place (000 being 1st, 100 2nd)
    list_display = ('name',)
    search_fields = ('name',)


modeladmin_register(IndicatorAdmin)
