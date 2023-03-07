from django.contrib import admin
from django.contrib.admin.utils import quote
from django.http import HttpResponse
from django.urls import re_path
from django.utils.text import slugify
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
    download_report_button_classnames = ['icon', 'icon-fa-download']

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

    def download_report_button(self, report_pk, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.download_report_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('download', quote(report_pk)),
            'label': _("Download XLSX"),
            'classname': cn,
            'title': _("Download report as spreadsheet file"),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)
        buttons.append(self.download_report_button(obj.pk, **kwargs))
        return buttons


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

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        download_report_url = re_path(
            self.url_helper.get_action_url_pattern('download'),
            self.download_report_view,
            name=self.url_helper.get_action_url_name('download')
        )
        return urls + (
            download_report_url,
        )

    def download_report_view(self, request, instance_pk):
        report = Report.objects.get(pk=instance_pk)
        output = report.to_xlsx()
        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        filename = slugify(report.name, allow_unicode=True) + '.xlsx'
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response
