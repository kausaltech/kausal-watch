from django.utils.translation import gettext_lazy as _
from django.db.models import Q
from wagtail.core import hooks
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, RichTextFieldPanel, 
)
from wagtailautocomplete.edit_handlers import AutocompletePanel
from generic_chooser.views import ModelChooserViewSet
from generic_chooser.widgets import AdminChooser

from admin_site.wagtail import AdminOnlyPanel, AplansModelAdmin, AplansTabbedInterface
from .admin import DisconnectedIndicatorFilter
from .models import (
    Indicator, Quantity, Dataset
)


class IndicatorPermissionHelper(PermissionHelper):
    def user_can_inspect_obj(self, user, obj):
        if not super().user_can_inspect_obj(user, obj):
            return False

        # The user has view permission to all actions if he is either
        # a general admin for actions or a contact person for any
        # actions.
        if user.is_superuser:
            return True

        adminable_plans = user.get_adminable_plans()
        obj_plans = obj.plans.all()
        for plan in adminable_plans:
            if plan in obj_plans:
                return True

        return False

    def user_can_edit_obj(self, user, obj):
        if not super().user_can_edit_obj(user, obj):
            return False

        obj_plans = obj.plans.all()
        for plan in obj_plans:
            if user.is_general_admin_for_plan(plan):
                return True

        # FIXME: Indicator contact persons
        return False

    def user_can_delete_obj(self, user, obj):
        if not super().user_can_delete_obj(user, obj):
            return False

        return self.user_can_edit_obj(user, obj)

    def user_can_create(self, user):
        if not super().user_can_create(user):
            return False

        plan = user.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            return True
        return False


class QuantityChooserViewSet(ModelChooserViewSet):
    icon = 'user'
    model = Quantity
    page_title = _("Choose a quantity")
    per_page = 10
    order_by = 'name'
    fields = ['name']


class QuantityChooser(AdminChooser):
    choose_one_text = _('Choose a quantity')
    choose_another_text = _('Choose another quantity')
    link_to_chosen_text = _('Edit this quantity')
    model = Quantity
    choose_modal_url_name = 'quantity_chooser:choose'


@hooks.register('register_admin_viewset')
def register_quantity_chooser_viewset():
    return QuantityChooserViewSet('quantity_chooser', url_prefix='quantity-chooser')


class IndicatorAdmin(AplansModelAdmin):
    model = Indicator
    menu_icon = 'fa-bar-chart'  # change as required
    menu_order = 3
    menu_label = _('Indicators')
    list_display = ('name', 'unit', 'quantity', 'has_data',)
    list_filter = (DisconnectedIndicatorFilter,)
    search_fields = ('name',)
    permission_helper_class = IndicatorPermissionHelper

    panels = [
        FieldPanel('name'),
        FieldPanel('quantity'),
        FieldPanel('unit'),
        FieldPanel('time_resolution'),
        RichTextFieldPanel('description'),
        FieldPanel('datasets'),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(Q(plans=plan) | Q(plans__isnull=True)).distinct().select_related('unit', 'quantity')


modeladmin_register(IndicatorAdmin)
