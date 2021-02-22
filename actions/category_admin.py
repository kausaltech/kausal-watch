from django.utils.translation import gettext_lazy as _
from wagtail.admin.edit_handlers import (
    FieldPanel, FieldRowPanel, MultiFieldPanel,
)
from wagtail.contrib.modeladmin.options import ModelAdminGroup, modeladmin_register
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailorderable.modeladmin.mixins import OrderableMixin

from admin_site.wagtail import (
    AplansModelAdmin, CondensedInlinePanel, PlanFilteredFieldPanel
)

from .admin import CategoryTypeFilter
from .models import Category, CategoryType, CategoryTypeMetadata


class CategoryTypeAdmin(AplansModelAdmin):
    model = CategoryType
    menu_icon = 'fa-briefcase'
    menu_label = _('Category types')
    menu_order = 1
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        MultiFieldPanel([
            FieldRowPanel([
                FieldPanel('usable_for_actions'),
                FieldPanel('editable_for_actions'),
            ]),
            FieldRowPanel([
                FieldPanel('usable_for_indicators'),
                FieldPanel('editable_for_indicators'),
            ]),
        ], heading=_('Action and indicator categorization'), classname='collapsible collapsed'),
        CondensedInlinePanel('levels', panels=[
            FieldPanel('name',)
        ]),
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


class CategoryTypeMetadataAdmin(AplansModelAdmin):
    model = CategoryTypeMetadata
    menu_label = _('Category metadata')
    list_display = ('name', 'type')

    panels = [
        PlanFilteredFieldPanel('type'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('format'),
        CondensedInlinePanel('choices', panels=[
            FieldPanel('name'),
            FieldPanel('identifier'),
        ])
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(type__plan=plan).distinct()


class CategoryAdmin(OrderableMixin, AplansModelAdmin):
    menu_label = _('Categories')
    list_display = ('__str__', 'parent', 'type')
    list_filter = (CategoryTypeFilter,)
    model = Category

    panels = [
        PlanFilteredFieldPanel('type'),
        PlanFilteredFieldPanel('parent'),
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('short_description'),
        ImageChooserPanel('image'),
        FieldPanel('color'),
    ]

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        plan = user.get_active_admin_plan()
        return qs.filter(type__plan=plan).distinct()


class CategoryGroup(ModelAdminGroup):
    menu_order = 2
    menu_label = _('Categories')
    items = (CategoryTypeAdmin, CategoryTypeMetadataAdmin, CategoryAdmin)


modeladmin_register(CategoryGroup)
