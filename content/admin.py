from django.contrib import admin

from ckeditor.widgets import CKEditorWidget

from aplans.utils import public_fields
from .models import SiteGeneralContent


@admin.register(SiteGeneralContent)
class SiteGeneralContentAdmin(admin.ModelAdmin):
    fields = list(set(public_fields(SiteGeneralContent)) - set(['id']))

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['hero_content'].widget = CKEditorWidget()
        form.base_fields['action_list_lead_content'].widget = CKEditorWidget()
        form.base_fields['indicator_list_lead_content'].widget = CKEditorWidget()
        form.base_fields['dashboard_lead_content'].widget = CKEditorWidget()
        return form

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def has_add_permission(self, request, obj=None):
        plan = request.user.get_active_admin_plan()
        if SiteGeneralContent.objects.filter(plan=plan).exists():
            return False
        return request.user.is_general_admin_for_plan(plan)

    def has_delete_permission(self, request, obj=None):
        return False

    def save_model(self, request, obj, form, change):
        obj.plan = request.user.get_active_admin_plan()
        super().save_model(request, obj, form, change)
