from django.utils.translation import gettext_lazy as _
from django import forms
from wagtail.admin.edit_handlers import (
    FieldPanel, FieldRowPanel, MultiFieldPanel, ObjectList,
)
from wagtail.contrib.modeladmin.options import ModelAdminGroup, modeladmin_register
from wagtail.core.fields import RichTextField
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.core.rich_text import RichText
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailorderable.modeladmin.mixins import OrderableMixin

from admin_site.wagtail import (
    AplansModelAdmin, CondensedInlinePanel, PlanFilteredFieldPanel, AplansTabbedInterface
)

from .admin import CategoryTypeFilter
from .models import Category, CategoryMetadataRichText, CategoryType, CategoryTypeMetadata


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
            FieldPanel('name',),
            FieldPanel('name_plural',)
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


class CategoryTypeMetadataAdmin(OrderableMixin, AplansModelAdmin):
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


def get_metadata_fields(cat_type, obj, with_initial=False):
    fields = {}

    if not obj or not obj.pk:
        with_initial = False

    for metadata in cat_type.metadata.all():
        initial = None
        if metadata.format == CategoryTypeMetadata.MetadataFormat.ORDERED_CHOICE:
            qs = metadata.choices.all()
            if with_initial:
                c = metadata.category_choices.filter(category=obj).first()
                if c:
                    initial = c.choice
            field = forms.ModelChoiceField(
                qs, label=metadata.name, initial=initial, required=False,
            )
        else:
            initial = None
            if with_initial:
                val_obj = metadata.category_richtexts.filter(category=obj).first()
                if val_obj is not None:
                    initial = val_obj.text

            field = CategoryMetadataRichText._meta.get_field('text').formfield(
                initial=initial, required=False
            )

        field.metadata = metadata
        fields['metadata_%s' % metadata.identifier] = field
    return fields


class MetadataFieldPanel(FieldPanel):
    def on_form_bound(self):
        super().on_form_bound()
        metadata_fields = get_metadata_fields(self.instance.type, self.instance, with_initial=True)
        self.form.fields[self.field_name].initial = metadata_fields[self.field_name].initial


class CategoryAdminForm(WagtailAdminModelForm):
    def save(self, commit=True):
        obj = super().save(commit)

        # Update categories
        for field_name, field in get_metadata_fields(obj.type, obj).items():
            val = self.cleaned_data.get(field_name)
            field.metadata.set_category_value(obj, val)
        return obj


class CategoryEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        if self.instance is not None:
            metadata_fields = get_metadata_fields(self.instance.type, self.instance, with_initial=True)
        else:
            metadata_fields = {}

        self.base_form_class = type(
            'CategoryAdminForm',
            (CategoryAdminForm,),
            metadata_fields
        )
        return super().get_form_class()


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

    def get_edit_handler(self, instance, request):
        tabs = [ObjectList(self.panels, heading=_('Basic information'))]

        if instance and instance.type:
            metadata_fields = get_metadata_fields(instance.type, instance, with_initial=True)
        else:
            metadata_fields = {}

        metadata_panels = []
        for key, field in metadata_fields.items():
            metadata_panels.append(MetadataFieldPanel(key, heading=field.metadata.name))

        tabs.append(ObjectList(metadata_panels, heading=_('Categories')))
        return CategoryEditHandler(tabs)


class CategoryGroup(ModelAdminGroup):
    menu_order = 400
    menu_label = _('Categories')
    items = (CategoryTypeAdmin, CategoryTypeMetadataAdmin, CategoryAdmin)


modeladmin_register(CategoryGroup)
