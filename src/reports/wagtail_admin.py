from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from django.contrib import messages
from django.contrib.admin.utils import quote
from django.urls import path, reverse
from django.utils.translation import gettext_lazy as _
from wagtail.admin.filters import WagtailFilterSet
from wagtail.admin.panels import FieldPanel
from wagtail.admin.ui.tables import BooleanColumn
from wagtail.admin.widgets.button import ListingButton
from wagtail.snippets.models import register_snippet

from django_filters import filters

from kausal_common.users import user_or_bust, user_or_none

from aplans.utils import append_query_parameter

from admin_site.viewsets import WatchCreateView, WatchDeleteView, WatchEditView, WatchIndexView, WatchViewSet

from .models import Report, ReportType
from .usage import get_report_type_usage
from .views import DownloadReportView, MarkReportAsCompleteView

if TYPE_CHECKING:
    from django.http import HttpRequest


class ReportTypeDeleteView(WatchDeleteView[ReportType]):
    """
    Refuse to delete a report type that a report comparison block still refers to.

    Deleting such a report type would break the action details pages, and admins have mistaken deleting the report
    type for removing the block.
    """

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['usage'] = get_report_type_usage(self.object)
        return context

    def post(self, request, *args, **kwargs):
        if get_report_type_usage(self.object).blocks_deletion:
            messages.error(
                request,
                _('The report type is still used on action pages. Remove the report comparison blocks first.'),
            )
            return self.get(request, *args, **kwargs)
        return super().post(request, *args, **kwargs)


class ReportTypeViewSet(WatchViewSet[ReportType]):
    model = ReportType
    menu_label = _('Report types')
    icon = 'doc-full'
    menu_order = 1200
    add_to_settings_menu = True
    url_prefix = 'plan_reports/report_type'
    delete_view_class = ReportTypeDeleteView
    bulk_delete_enabled = False
    delete_template_name = 'reports/report_type_delete.html'

    panels = [
        FieldPanel('name'),
        FieldPanel('only_plan_admins_can_mark_actions_as_complete'),
        FieldPanel('fields', heading=_('fields')),
    ]

    def get_queryset(self, request: HttpRequest):
        plan = user_or_bust(request.user).get_active_admin_plan()
        return ReportType.objects.filter(plan=plan)


register_snippet(ReportTypeViewSet)


class ReportTypeQueryParameterMixin:
    """Keep the listing's `report_type` filter in the URLs the report views link to."""

    request: HttpRequest

    def with_report_type(self, url: str | None) -> str | None:
        if url is None or '?' in url:
            return url
        return append_query_parameter(self.request, url, 'report_type')


class ReportCreateView(ReportTypeQueryParameterMixin, WatchCreateView[Report]):
    def initialize_instance(self, request: HttpRequest, instance: Report) -> None:
        """Set the new report's type to the one given in the GET data."""
        report_type = request.GET.get('report_type')
        if not report_type:
            return
        instance.type = ReportType.objects.get(pk=int(report_type))

    def get_add_url(self):
        return self.with_report_type(super().get_add_url())

    def get_edit_url(self):
        return self.with_report_type(super().get_edit_url())

    def get_success_url(self):
        return self.with_report_type(super().get_success_url())


class ReportEditView(ReportTypeQueryParameterMixin, WatchEditView[Report]):
    def get_edit_url(self):
        return self.with_report_type(super().get_edit_url())

    def get_delete_url(self):
        return self.with_report_type(super().get_delete_url())

    def get_success_url(self):
        return self.with_report_type(super().get_success_url())


class ReportDeleteView(ReportTypeQueryParameterMixin, WatchDeleteView[Report]):
    def get_delete_url(self):
        return self.with_report_type(super().get_delete_url())

    def get_success_url(self):
        return self.with_report_type(super().get_success_url())


class ReportIndexView(ReportTypeQueryParameterMixin, WatchIndexView[Report]):
    download_url_name: ClassVar[str | None] = None
    mark_as_complete_url_name: ClassVar[str | None] = None
    undo_marking_as_complete_url_name: ClassVar[str | None] = None

    def get_add_url(self):
        # A report needs a type, which only the menu item of each report type gives
        if 'report_type' not in self.request.GET:
            return None
        return self.with_report_type(super().get_add_url())

    def get_edit_url(self, instance: Report):
        return self.with_report_type(super().get_edit_url(instance))

    def get_delete_url(self, instance: Report):
        return self.with_report_type(super().get_delete_url(instance))

    def _report_url(self, url_name: str | None, instance: Report) -> str:
        assert url_name is not None
        return reverse(url_name, args=(quote(instance.pk),))

    def get_list_more_buttons(self, instance: Report):
        buttons = list(super().get_list_more_buttons(instance))
        buttons.append(
            ListingButton(
                _('Download XLSX'),
                url=self._report_url(self.download_url_name, instance),
                icon_name='download',
                attrs={'title': _('Download report as spreadsheet file')},
                priority=40,
            )
        )
        if instance.is_complete:
            button = ListingButton(
                _('Undo marking as complete'),
                url=self._report_url(self.undo_marking_as_complete_url_name, instance),
                icon_name='fontawesome-rotate-left',
                attrs={'title': _('Undo marking this report as complete')},
                priority=50,
            )
        else:
            button = ListingButton(
                _('Mark as complete'),
                url=self._report_url(self.mark_as_complete_url_name, instance),
                icon_name='check',
                attrs={'title': _('Mark this report as complete')},
                priority=50,
            )
        buttons.append(button)
        return buttons


def report_types_for_request(request: HttpRequest | None):
    user = user_or_none(request.user) if request is not None else None
    if user is None:
        return ReportType.objects.none()
    return user.get_active_admin_plan().report_types.all()


class ReportFilterSet(WagtailFilterSet):
    report_type = filters.ModelChoiceFilter(
        field_name='type',
        queryset=report_types_for_request,  # pyright: ignore[reportArgumentType]
        label=_('Report type'),
    )

    class Meta:
        model = Report
        fields = ['report_type']


class ReportViewSet(WatchViewSet[Report]):
    model = Report
    # Each report type has its own menu item instead
    add_to_admin_menu = False
    menu_item_is_registered = True
    icon = 'doc-full'
    url_prefix = 'plan_reports/report'
    list_display = ['name', BooleanColumn('is_complete'), BooleanColumn('is_public')]
    filterset_class = ReportFilterSet
    index_view_class = ReportIndexView
    add_view_class = ReportCreateView
    edit_view_class = ReportEditView
    delete_view_class = ReportDeleteView
    bulk_delete_enabled = False
    download_url_name = 'download'
    mark_as_complete_url_name = 'mark_report_as_complete'
    undo_marking_as_complete_url_name = 'undo_marking_report_as_complete'

    panels = [
        FieldPanel('name'),
        FieldPanel('start_date'),
        FieldPanel('end_date'),
        FieldPanel('is_public'),
        FieldPanel('show_in_reporting_tab'),
    ]

    def get_queryset(self, request: HttpRequest):
        plan = user_or_bust(request.user).get_active_admin_plan()
        return Report.objects.filter(type__plan=plan)

    def get_common_view_kwargs(self, **kwargs):
        return super().get_common_view_kwargs(
            download_url_name=self.get_url_name(self.download_url_name),
            mark_as_complete_url_name=self.get_url_name(self.mark_as_complete_url_name),
            undo_marking_as_complete_url_name=self.get_url_name(self.undo_marking_as_complete_url_name),
            **kwargs,
        )

    @property
    def download_view(self):
        return self.construct_view(DownloadReportView)

    @property
    def mark_as_complete_view(self):
        return self.construct_view(MarkReportAsCompleteView, complete=True)

    @property
    def undo_marking_as_complete_view(self):
        return self.construct_view(MarkReportAsCompleteView, complete=False)

    def get_urlpatterns(self):
        return [
            *super().get_urlpatterns(),
            path(f'{self.download_url_name}/<str:pk>/', self.download_view, name=self.download_url_name),
            path(
                f'{self.mark_as_complete_url_name}/<str:pk>/',
                self.mark_as_complete_view,
                name=self.mark_as_complete_url_name,
            ),
            path(
                f'{self.undo_marking_as_complete_url_name}/<str:pk>/',
                self.undo_marking_as_complete_view,
                name=self.undo_marking_as_complete_url_name,
            ),
        ]


register_snippet(ReportViewSet)
