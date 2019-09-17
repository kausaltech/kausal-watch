from django.contrib import admin

from admin_ordering.admin import OrderableAdmin
from ckeditor.widgets import CKEditorWidget

from .models import StaticPage, BlogPost, Question


@admin.register(StaticPage)
class StaticPageAdmin(admin.ModelAdmin, OrderableAdmin):
    list_display = ('title', 'is_published', 'order')
    fields = ['title', 'slug', 'parent', 'order', 'is_published', 'content']
    ordering_field = 'order'
    ordering_field_hide_input = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        plan = request.user.get_active_admin_plan()

        form.base_fields['content'].widget = CKEditorWidget()

        field = form.base_fields['parent']
        qs = field.queryset
        if obj is not None:
            qs = qs.exclude(id=obj.id)
        field.queryset = qs.filter(plan=plan)

        return form

    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        obj.plan = request.user.get_active_admin_plan()
        super().save_model(request, obj, form, change)


@admin.register(BlogPost)
class BlogPostAdmin(admin.ModelAdmin):
    list_display = ('title', 'is_published', 'published_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['content'].widget = CKEditorWidget()
        return form


@admin.register(Question)
class QuestionAdmin(OrderableAdmin, admin.ModelAdmin):
    list_display = ('title',)
    fields = ['order', 'title', 'answer']
    ordering_field = 'order'
    ordering_field_hide_input = True

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['answer'].widget = CKEditorWidget()
        return form

    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        obj.plan = request.user.get_active_admin_plan()
        super().save_model(request, obj, form, change)
