from django.utils.translation import gettext_lazy as _
from django.conf import settings
from django import forms
from wagtail.admin.forms import WagtailAdminModelForm
from wagtail.contrib.modeladmin.options import ModelAdmin, modeladmin_register
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, RichTextFieldPanel, TabbedInterface, ObjectList
)
from wagtail.images.edit_handlers import ImageChooserPanel
from modeltrans.translator import get_i18n_field
from django_orghierarchy.models import Organization

from .models import Action, Plan


class ActionForm(WagtailAdminModelForm):
    pass


class ActionEditHandler(TabbedInterface):
    def on_request_bound(self):
        """
        for child in list(self.children):
            if isinstance(child, AdminOnlyPanel):
                self.children.remove(child)
        """
        super().on_request_bound()

    def on_form_bound(self):
        form = self.form
        user = self.request.user
        plan = user.get_active_admin_plan()

        if plan.actions_locked:
            form.fields['identifier'].disabled = True
            form.fields['identifier'].required = False
            form.fields['official_name'].disabled = True
            form.fields['official_name'].required = False

        if 'impact' in form.fields:
            form._meta.exclude = ['impact']
            del form.fields['impact']

        #f = form.fields['impact']
        #f.queryset = f.queryset.filter(plan=plan)

        super().on_form_bound()


class AdminOnlyPanel(ObjectList):
    pass


class ActionAdmin(ModelAdmin):
    model = Action
    menu_icon = 'wagtail'  # change as required
    menu_order = 201  # will put in 3rd place (000 being 1st, 100 2nd)
    exclude_from_explorer = False  # or True to exclude pages of this type from Wagtail's explorer view
    list_display = ('identifier', 'name')
    # list_filter = ('author',)
    search_fields = ('identifier', 'name')
    list_display_add_buttons = 'name'

    basic_panels = [
        FieldPanel('identifier'),
        FieldPanel('official_name'),
        FieldPanel('name', classname='full title'),
        RichTextFieldPanel('description'),
    ]

    internal_panel = AdminOnlyPanel([
        FieldPanel('internal_priority'),
        FieldPanel('internal_priority_comment'),
        FieldPanel('impact'),
    ], heading=_('Internal information'))

    edit_handler = ActionEditHandler([
        ObjectList(basic_panels, heading=_('Basic information')),
        internal_panel,
        ObjectList([InlinePanel('responsible_parties')], heading=_('Responsibles')),
        ObjectList([InlinePanel('tasks')], heading=_('Tasks')),
    ])

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        if not request.user.is_general_admin_for_plan(plan):
            qs = qs.unmerged()
        return qs.filter(plan=plan)


modeladmin_register(ActionAdmin)


class PlanAdmin(ModelAdmin):
    model = Plan
    menu_icon = 'wagtail'  # change as required
    menu_order = 200  # will put in 3rd place (000 being 1st, 100 2nd)
    exclude_from_explorer = False  # or True to exclude pages of this type from Wagtail's explorer view
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('actions_locked'),
        FieldPanel('allow_images_for_actions'),
    ]

    def get_edit_handler(self, instance, request):
        i18n_field = get_i18n_field(type(instance))
        tabs = [ObjectList(self.panels, heading='Perustiedot')]
        if i18n_field:
            for lang_code, name in settings.LANGUAGES:
                if lang_code == 'fi':
                    continue
                fields = []
                for field in i18n_field.get_translated_fields():
                    if field.language != lang_code:
                        continue
                    fields.append(FieldPanel(field.name))
                tabs.append(ObjectList(fields, heading=name))

        handler = TabbedInterface(tabs)
        return handler


modeladmin_register(PlanAdmin)


# Monkeypatch Organization to support Wagtail autocomplete
def org_autocomplete_label(self):
    return self.name


Organization.autocomplete_search_field = 'distinct_name'
Organization.autocomplete_label = org_autocomplete_label
