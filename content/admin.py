from django.contrib import admin

from admin_ordering.admin import OrderableAdmin
from ckeditor.widgets import CKEditorWidget
from image_cropping import ImageCroppingMixin

from aplans.utils import public_fields
from .models import StaticPage, BlogPost, Question, SiteGeneralContent


@admin.register(BlogPost)
class BlogPostAdmin(ImageCroppingMixin, admin.ModelAdmin):
    list_display = ('title', 'is_published', 'published_at')

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        return qs.filter(plan=plan)

    def get_form(self, request, obj=None, **kwargs):
        form = super().get_form(request, obj, **kwargs)
        form.base_fields['content'].widget = CKEditorWidget()
        return form


class QuestionAdmin(OrderableAdmin, admin.StackedInline):
    model = Question

    list_display = ('title',)
    fields = ['order', 'title', 'answer']
    ordering_field = 'order'
    ordering_field_hide_input = True

    def get_formset(self, *args, **kwargs):
        formset = super().get_formset(*args, **kwargs)
        formset.form.base_fields['answer'].widget = CKEditorWidget(config_name='lite')
        return formset

    def save_model(self, request, obj, form, change):
        obj.modified_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(StaticPage)
class StaticPageAdmin(ImageCroppingMixin, admin.ModelAdmin, OrderableAdmin):
    list_display = ('title', 'is_published', 'order')
    fields = [
        'name', 'slug', 'parent', 'order', 'is_published', 'top_menu', 'footer',
        'title', 'tagline', 'image', 'image_cropping', 'content'
    ]
    ordering_field = 'order'
    ordering_field_hide_input = True

    inlines = [QuestionAdmin]

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
