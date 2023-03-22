from dal import autocomplete
from django.db.models import Q

from .models import Report, ReportType
from aplans.types import WatchAdminRequest


class ReportTypeAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: ReportType):
        return str(result)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return ReportType.objects.none()

        plan = self.request.get_active_admin_plan()

        report_types = plan.report_types.all()
        if self.q:
            q = self.q.strip()
            report_types = report_types.filter(
                Q(identifier__istartswith=q) |
                Q(name__icontains=q)
            )
        return report_types


class ReportAutocomplete(autocomplete.Select2QuerySetView):
    request: WatchAdminRequest

    def get_result_label(self, result: Report):
        return str(result)

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Report.objects.none()

        plan = self.request.get_active_admin_plan()

        report_types = plan.report_types.all()
        reports = Report.objects.filter(type__in=report_types)
        if self.q:
            q = self.q.strip()
            reports = reports.filter(
                Q(identifier__istartswith=q) |
                Q(name__icontains=q)
            )
        return reports


def get_report_field_choice_list(request):
    if not request.user.is_authenticated:
        return []
    result = []
    plan = request.get_active_admin_plan()
    for report_type in plan.report_types.all():
        for field in report_type.fields:
            name = getattr(field.value, 'name', None)
            if name:
                result.append((field.id, name))
    return result


class ReportTypeFieldAutocomplete(autocomplete.Select2ListView):
    request: WatchAdminRequest

    def get_list(self):
        return get_report_field_choice_list(self.request)
