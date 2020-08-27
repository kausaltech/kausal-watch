import json
import itertools
from datetime import datetime

from django.utils.translation import gettext_lazy as _
from django.utils.functional import cached_property
from django.http.response import HttpResponseBadRequest, HttpResponse
from django.db.models import Q
from django.urls import re_path, reverse
from wagtail.core import hooks
from wagtail.contrib.modeladmin.options import (
    modeladmin_register, ModelAdminGroup
)
from wagtail.contrib.modeladmin.helpers import PermissionHelper
from wagtail.contrib.modeladmin.views import InstanceSpecificView
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, RichTextFieldPanel, 
)
from wagtailautocomplete.edit_handlers import AutocompletePanel
from generic_chooser.views import ModelChooserViewSet
from generic_chooser.widgets import AdminChooser

from admin_site.wagtail import (
    AdminOnlyPanel, AplansModelAdmin, AplansTabbedInterface,
    CondensedInlinePanel
)
from .admin import DisconnectedIndicatorFilter
from .models import (
    Indicator, Quantity, Dataset, Dimension
)
from .api import IndicatorValueSerializer, IndicatorViewSet


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


class EditValuesView(InstanceSpecificView):
    template_name = 'indicators/edit_values.html'

    @cached_property
    def edit_values_url(self):
        return self.url_helper.get_action_url('edit_values', self.pk_quoted)

    def check_action_permitted(self, user):
        return self.permission_helper.user_can_edit_obj(user, self.instance)

    def make_categories(self, cats):
        return [dict(id=cat.id, name=cat.name) for cat in cats]

    def get_dimensions(self, obj):
        dims = [
            d.dimension for d in obj.dimensions.select_related('dimension').prefetch_related('dimension__categories')
        ]
        for idx, dim in enumerate(dims):
            dim.order = idx
        return dims

    def get_context_data(self, **kwargs):
        obj = self.instance
        context = super().get_context_data(**kwargs)
        dims = self.get_dimensions(obj)
        dims_by_id = {dim.id: dim for dim in dims}

        dims_out = [{
            'id': dim.id,
            'name': dim.name,
            'order': dim.order,
            'categories': self.make_categories(dim.categories.all())
        } for dim in dims]
        context['dimensions'] = json.dumps(dims_out)

        value_qs = obj.values.order_by('date').prefetch_related('categories')
        data = IndicatorValueSerializer(value_qs, many=True).data

        """
        def make_key(obj):
            cats = list(obj.categories.all())
            if not cats:
                return 'default'

            cat_ids = [None] * len(dims)
            for cat in cats:
                dim = dims_by_id[cat.dimension_id]
                assert cat_ids[dim.order] is None
                cat_ids[dim.order] = cat.id
            return ('-'.join([str(x) for x in cat_ids]))

        for date, values in itertools.groupby(value_qs, key=lambda x: x.date.isoformat()):
            d = {make_key(obj): obj.value for obj in values}
            out.append(dict(date=date, **d))
        """

        context['values'] = json.dumps(data)
        context['post_values_uri'] = reverse('indicator-values', kwargs=dict(pk=self.pk_quoted))

        return context


class DimensionAdmin(AplansModelAdmin):
    model = Dimension
    menu_order = 4
    menu_label = _('Indicator dimensions')
    list_display = ('name',)

    panels = [
        FieldPanel('name'),
        CondensedInlinePanel('categories', panels=[FieldPanel('name')]),
    ]


class IndicatorAdmin(AplansModelAdmin):
    model = Indicator
    menu_icon = 'fa-bar-chart'
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
        CondensedInlinePanel('dimensions'),
    ]

    def edit_values_view(self, request, instance_pk):
        kwargs = {'model_admin': self, 'instance_pk': instance_pk}
        view_class = EditValuesView
        return view_class.as_view(**kwargs)(request)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(Q(plans=plan) | Q(plans__isnull=True)).distinct().select_related('unit', 'quantity')

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        urls += (
            re_path(
                self.url_helper.get_action_url_pattern('edit_values'),
                self.edit_values_view,
                name=self.url_helper.get_action_url_name('edit_values')
            ),
        )
        return urls


class IndicatorGroup(ModelAdminGroup):
    menu_label = _('Indicators')
    menu_icon = 'fa-bar-chart'
    menu_order = 3
    items = (IndicatorAdmin, DimensionAdmin,)


modeladmin_register(IndicatorGroup)
