from django.contrib import admin
from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import FieldPanel, StreamFieldPanel
from wagtail.contrib.modeladmin.helpers import ButtonHelper
from wagtail.contrib.modeladmin.menus import ModelAdminMenuItem
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.contrib.modeladmin.views import DeleteView

from .models import Report, ReportType
from admin_site.wagtail import AplansCreateView, AplansEditView, AplansModelAdmin
from aplans.utils import append_query_parameter


# FIXME: Duplicated code in category_admin.py and attribute_type_admin.py
class ReportTypeQueryParameterMixin:
    @property
    def index_url(self):
        return append_query_parameter(self.request, super().index_url, 'report_type')

    @property
    def create_url(self):
        return append_query_parameter(self.request, super().create_url, 'report_type')

    @property
    def edit_url(self):
        return append_query_parameter(self.request, super().edit_url, 'report_type')

    @property
    def delete_url(self):
        return append_query_parameter(self.request, super().delete_url, 'report_type')


class ReportCreateView(ReportTypeQueryParameterMixin, AplansCreateView):
    def get_instance(self):
        """Create a report instance and set its report type to the one given in the GET or POST data."""
        instance = super().get_instance()
        report_type = self.request.GET.get('report_type')
        if report_type and not instance.pk:
            assert not hasattr(instance, 'type')
            instance.type = ReportType.objects.get(pk=int(report_type))
            instance.fields = instance.type.fields
        return instance


class ReportEditView(ReportTypeQueryParameterMixin, AplansEditView):
    pass


class ReportDeleteView(ReportTypeQueryParameterMixin, DeleteView):
    pass


class ReportAdminButtonHelper(ButtonHelper):
    # TODO: duplicated as AttributeTypeAdminButtonHelper
    def add_button(self, *args, **kwargs):
        """
        Only show "add" button if the request contains a report type.

        Set GET parameter report_type to the type for the URL when clicking the button.
        """
        if 'report_type' in self.request.GET:
            data = super().add_button(*args, **kwargs)
            data['url'] = append_query_parameter(self.request, data['url'], 'report_type')
            return data
        return None

    def inspect_button(self, *args, **kwargs):
        data = super().inspect_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'report_type')
        return data

    def edit_button(self, *args, **kwargs):
        data = super().edit_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'report_type')
        return data

    def delete_button(self, *args, **kwargs):
        data = super().delete_button(*args, **kwargs)
        data['url'] = append_query_parameter(self.request, data['url'], 'report_type')
        return data


@modeladmin_register
class ReportTypeAdmin(AplansModelAdmin):
    model = ReportType
    menu_label = _('Report types')
    menu_icon = 'doc-full'
    menu_order = 1200
    add_to_settings_menu = True

    panels = [
        FieldPanel('name'),
        StreamFieldPanel('fields', heading=_('fields')),
    ]

    def get_form_fields_exclude(self, request):
        exclude = super().get_form_fields_exclude(request)
        exclude += ['plan']
        return exclude

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(plan=plan)

    # def get_edit_handler(self, instance, request):
    #     panels = list(self.panels)
    #     if instance and instance.common:
    #         panels.insert(1, FieldPanel('common'))
    #     tabs = [ObjectList(panels, heading=_('Basic information'))]
    #
    #     i18n_tabs = get_translation_tabs(instance, request)
    #     tabs += i18n_tabs
    #
    #     return CategoryTypeEditHandler(tabs)


class ReportTypeFilter(admin.SimpleListFilter):
    title = _('Report type')
    parameter_name = 'report_type'

    def lookups(self, request, model_admin):
        user = request.user
        plan = user.get_active_admin_plan()
        choices = [(i.id, i.name) for i in plan.report_types.all()]
        return choices

    def queryset(self, request, queryset):
        if self.value() is not None:
            return queryset.filter(type=self.value())
        else:
            return queryset


class ReportAdminMenuItem(ModelAdminMenuItem):
    def is_shown(self, request):
        # Hide it because we will have menu items for listing reports of specific types.
        # Note that we need to register ReportAdmin nonetheless, otherwise the URLs wouldn't be set up.
        return False


@modeladmin_register
class ReportAdmin(AplansModelAdmin):
    model = Report
    menu_label = _('Reports')
    list_display= ('name', 'is_complete', 'is_public')
    list_filter = (ReportTypeFilter,)

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('start_date'),
        FieldPanel('end_date'),
        FieldPanel('is_complete'),
        FieldPanel('is_public'),
    ]

    create_view_class = ReportCreateView
    edit_view_class = ReportEditView
    # Do we need to create a view for inspect_view?
    delete_view_class = ReportDeleteView
    button_helper_class = ReportAdminButtonHelper

    def get_menu_item(self, order=None):
        return ReportAdminMenuItem(self, order or self.get_menu_order())

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(type__plan=plan).distinct()
