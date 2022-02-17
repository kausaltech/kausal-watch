from ckeditor.widgets import CKEditorWidget
from django import forms
from django.contrib import admin

from admin_site.admin import AplansModelAdmin

from .models import BaseTemplate, ContentBlock, NotificationTemplate


@admin.register(BaseTemplate)
class BaseTemplateAdmin(AplansModelAdmin):
    fields = [
        'from_name',
        'from_address',
        'reply_to',
        'brand_dark_color',
        'logo',
        'font_family',
        'font_css_url',
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def save_model(self, request, obj, form, change):
        obj.plan = request.user.get_active_admin_plan()
        super().save_model(request, obj, form, change)


@admin.register(NotificationTemplate)
class NotificationTemplateAdmin(AplansModelAdmin):
    fields = [
        'subject',
        'type',
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(base__plan=plan)

    def save_model(self, request, obj, form, change):
        plan = request.user.get_active_admin_plan()
        obj.base = plan.notification_base_template
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)

        plan = request.user.get_active_admin_plan()
        qs = NotificationTemplate.objects.filter(base__plan=plan).values_list('type', flat=True)
        if obj is not None and obj.type:
            qs = qs.exclude(id=obj.id)
        existing_types = set(qs)

        choices = [x for x in form.base_fields['type'].choices if x[0] not in existing_types]
        form.base_fields['type'].choices = choices

        if 'content' in form.base_fields:
            form.base_fields['content'].widget = CKEditorWidget(config_name='lite')
        return form


@admin.register(ContentBlock)
class ContentBlockAdmin(AplansModelAdmin):
    fields = [
        'identifier',
        'content',
        'template',
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(base__plan=plan)

    def save_model(self, request, obj, form, change):
        plan = request.user.get_active_admin_plan()
        obj.base = plan.notification_base_template
        super().save_model(request, obj, form, change)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        plan = request.user.get_active_admin_plan()

        if 'content' in form.base_fields:
            form.base_fields['content'].widget = CKEditorWidget(config_name='lite')
        field = form.base_fields.get('template')
        if field:
            field.queryset = field.queryset.filter(base=plan.notification_base_template)
        return form
