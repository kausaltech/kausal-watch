import json
from django.utils.translation import gettext_lazy as _
from django.forms.widgets import Select
from django import forms
from wagtail.contrib.modeladmin.options import modeladmin_register

from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, RichTextFieldPanel, TabbedInterface, ObjectList,
    MultiFieldPanel
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.images.edit_handlers import ImageChooserPanel
from wagtailautocomplete.edit_handlers import AutocompletePanel
from django_orghierarchy.models import Organization

from admin_site.wagtail import (
    AdminOnlyPanel, AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel, PlanRelatedPermissionHelper,
)
from people.chooser import PersonChooser
from .admin import ModifiableActionsFilter, MergedActionsFilter, ImpactFilter
from .models import Action, Plan, ActionStatus, ActionImpact, ActionTask


def _get_category_fields(plan, model, obj, with_initial=False):
    fields = {}
    if model == Action:
        filter_name = 'editable_for_actions'
    # elif self.model == Indicator:
    #     filter_name = 'editable_for_indicators'
    else:
        raise Exception()

    for cat_type in plan.category_types.filter(**{filter_name: True}):
        qs = cat_type.categories.all()
        if obj and with_initial:
            initial = obj.categories.filter(type=cat_type)
        else:
            initial = None
        field = forms.ModelMultipleChoiceField(
            qs, label=cat_type.name, initial=initial, required=False,
        )
        field.category_type = cat_type
        fields['categories_%s' % cat_type.identifier] = field
    return fields


"""
class CategoryFieldPanel(MultiFieldPanel):
    def __init__(self, field_name, *args, **kwargs):
        if 'children' not in kwargs:
            kwargs['children'] = []
        self._field_name = field_name
        if 'heading' not in kwargs:
            kwargs['heading'] = _('Categories')
        super().__init__(*args, **kwargs)

    def clone_kwargs(self):
        kwargs = super().clone_kwargs()
        kwargs['field_name'] = self._field_name
        return kwargs

    def bind_to(self, model=None, instance=None, request=None, form=None):
        bound_request = request if request is not None else getattr(self, 'request')
        bound_model = model if model is not None else getattr(self, 'model')
        if bound_request is not None and bound_model is not None:
            plan = bound_request.user.get_active_admin_plan()
            cat_fields = _get_category_fields(plan, bound_model, instance, with_initial=True)
            self.children = [FieldPanel(name, heading=field.label) for name, field in cat_fields.items()]
        return super().bind_to(model, instance, request, form)

    def required_fields(self):
        fields = []
        for handler in self.children:
            fields.extend(handler.required_fields())
        return fields
"""


class CategoryFieldPanel(FieldPanel):
    def on_form_bound(self):
        super().on_form_bound()
        cat_fields = _get_category_fields(self.instance.plan, self.model, self.instance, with_initial=True)
        self.form.fields[self.field_name].initial = cat_fields[self.field_name].initial


class ActionPermissionHelper(PlanRelatedPermissionHelper):
    def get_plans(self, obj):
        return [obj.plan]

    def user_can_edit_obj(self, user, obj):
        if not super().user_can_edit_obj(user, obj):
            return False

        return user.can_modify_action(obj)

    def user_can_delete_obj(self, user, obj):
        if not super().user_can_delete_obj(user, obj):
            return False

        if not user.can_modify_action(obj):
            return False

        plan = obj.plan
        if plan.actions_locked:
            return False

        return True

    def user_can_create(self, user):
        if not super().user_can_create(user):
            return False

        if not user.can_modify_action(None):
            return False

        plan = user.get_active_admin_plan()
        if plan.actions_locked:
            return False

        return True


class ActionEditHandler(AplansTabbedInterface):
    def get_form_class(self, request=None):
        user = request.user
        plan = user.get_active_admin_plan()
        cat_fields = _get_category_fields(plan, Action, self.instance, with_initial=True)

        self.base_form_class = type(
            'ActionAdminForm',
            (WagtailAdminModelForm,),
            cat_fields
        )

        form_class = super().get_form_class()

        if plan.actions_locked:
            form_class.base_fields['identifier'].disabled = True
            form_class.base_fields['identifier'].required = False
            form_class.base_fields['official_name'].disabled = True
            form_class.base_fields['official_name'].required = False

        if not user.is_general_admin_for_plan(plan):
            for panel in list(self.children):
                if not isinstance(panel, AdminOnlyPanel):
                    continue
                for child in panel.children:
                    if isinstance(child, FieldPanel):
                        del form_class.base_fields[child.field_name]
                    elif isinstance(child, InlinePanel):
                        del form_class.formsets[child.relation_name]
                    else:
                        raise Exception('Invalid child panel: %s' % child)

        field = form_class.base_fields.get('impact')
        if field is not None:
            field.queryset = field.queryset.filter(plan=plan)

        field = form_class.base_fields.get('status')
        if field is not None:
            field.queryset = field.queryset.filter(plan=plan)

        return form_class


class CondensedPanelSingleSelect(Select):
    def format_value(self, value):
        if value is None:
            return ''
        return str(value)


class ActionAdmin(AplansModelAdmin):
    model = Action
    menu_icon = 'fa-cubes'  # change as required
    menu_label = _('Actions')
    menu_order = 1
    list_display = ('identifier', 'name_link')
    list_display_add_buttons = 'name_link'
    list_filter = (ModifiableActionsFilter, ImpactFilter, MergedActionsFilter)
    search_fields = ('identifier', 'name')
    permission_helper_class = ActionPermissionHelper

    basic_panels = [
        FieldPanel('identifier'),
        FieldPanel('official_name'),
        FieldPanel('name', classname='full title'),
        RichTextFieldPanel('description'),
    ]

    internal_panel = AdminOnlyPanel([
        FieldPanel('status'),
        FieldPanel('internal_priority'),
        FieldPanel('internal_priority_comment'),
        FieldPanel('impact'),
    ], heading=_('Internal information'))

    task_panels = [
        FieldPanel('name'),
        FieldPanel('due_at'),
        FieldPanel('state', widget=CondensedPanelSingleSelect),
        FieldPanel('completed_at'),
        RichTextFieldPanel('comment'),
    ]

    task_header_from_js = '''
        function getHeader(task) {
            var f = task.fields;
            var out = '';
            var stateMap = %(state_map)s;
            if (f.name.length > 80) {
                out = f.name.slice(0, 80) + '...';
            } else {
                out = f.name;
            }
            var stateStr = stateMap[f.state];
            if (f.state != 'completed' && f.state != 'cancelled' && f.due_at) {
                stateStr += ', DL: ' + f.due_at;
            }
            out += ' <span class="action-task-header-state">(' + stateStr + ')</span>'
            return out;
        }
        console.log(form);
        getHeader(form);
    '''

    def get_list_display(self, request):
        def name_link(obj):
            from django.utils.html import format_html

            if self.permission_helper.user_can_edit_obj(request.user, obj):
                url = self.url_helper.get_action_url('edit', obj.pk)
                return format_html('<a href="{}">{}</a>', url, obj.name)
            else:
                return obj.name
        name_link.short_description = _('Name')
        self.name_link = name_link

        return ('identifier', 'name_link')

    def get_task_header_formatter(self):
        states = {key: str(label) for key, label in list(ActionTask.STATES)}
        out = self.task_header_from_js % dict(state_map=json.dumps(states))
        return out

    def get_edit_handler(self, instance, request):
        panels = list(self.basic_panels)

        cat_fields = _get_category_fields(instance.plan, Action, instance, with_initial=True)
        cat_panels = []
        for key, field in cat_fields.items():
            cat_panels.append(CategoryFieldPanel(key, heading=field.label))
        if cat_panels:
            panels.insert(2, MultiFieldPanel(cat_panels, heading=_('Categories')))

        i18n_tabs = self.get_translation_tabs(instance, request)

        handler = ActionEditHandler([
            ObjectList(panels, heading=_('Basic information')),
            self.internal_panel,
            ObjectList([
                CondensedInlinePanel(
                    'contact_persons',
                    panels=[
                        FieldPanel('person', widget=PersonChooser),
                        FieldPanel('primary_contact')
                    ]
                )
            ], heading=_('Contact persons')),
            AdminOnlyPanel([
                InlinePanel(
                    'responsible_parties',
                    panels=[AutocompletePanel('organization')]
                )
            ], heading=_('Responsible parties')),
            ObjectList([
                CondensedInlinePanel(
                    'tasks',
                    panels=self.task_panels,
                    card_header_from_js_safe=self.get_task_header_formatter()
                )
            ], heading=_('Tasks')),
            *i18n_tabs
        ])
        return handler

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        if not request.user.is_general_admin_for_plan(plan):
            qs = qs.unmerged()
        return qs.filter(plan=plan)


modeladmin_register(ActionAdmin)


class PlanEditHandler(TabbedInterface):
    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        return form_class

    def on_form_bound(self):
        super().on_form_bound()
        plan = self.instance
        f = self.form.fields['main_image']
        f.queryset = f.queryset.model.objects.filter(
            collection__in=plan.root_collection.get_descendants(inclusive=True)
        )


class PlanAdmin(AplansModelAdmin):
    model = Plan
    menu_icon = 'fa-briefcase'
    menu_label = _('Plans')
    menu_order = 2
    exclude_from_explorer = False  # or True to exclude pages of this type from Wagtail's explorer view
    list_display = ('name',)
    search_fields = ('name',)

    panels = [
        FieldPanel('name'),
        FieldPanel('identifier'),
        FieldPanel('actions_locked'),
        FieldPanel('allow_images_for_actions'),
        FieldPanel('primary_language'),
        FieldPanel('other_languages'),
        ImageChooserPanel('main_image'),
    ]

    action_status_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
        FieldPanel('is_completed'),
    ]

    action_impact_panels = [
        FieldPanel('identifier'),
        FieldPanel('name'),
    ]

    def get_form_class(self, request=None):
        form_class = super().get_form_class()
        return form_class
    """
        if self.instance.actions_locked:
            form_class.base_fields['identifier'].disabled = True
            form_class.base_fields['identifier'].required = False
            form_class.base_fields['official_name'].disabled = True
            form_class.base_fields['official_name'].required = False
    """

    def get_edit_handler(self, instance, request):
        action_status_panels = self.insert_model_translation_tabs(
            ActionStatus, self.action_status_panels, request, instance
        )
        action_impact_panels = self.insert_model_translation_tabs(
            ActionImpact, self.action_impact_panels, request, instance
        )
        panels = self.insert_model_translation_tabs(
            Plan, self.panels, request, instance
        )

        tabs = [
            ObjectList(panels, heading=_('Basic information')),
            ObjectList([
                CondensedInlinePanel('action_statuses', panels=action_status_panels, heading=_('Action statuses')),
                CondensedInlinePanel('action_impacts', panels=action_impact_panels, heading=_('Action impacts')),

            ], heading=_('Action classifications')),
        ]

        handler = PlanEditHandler(tabs)
        return handler

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        user = request.user
        if not user.is_superuser:
            qs = qs.filter(general_admins=user).distinct()
        return qs


modeladmin_register(PlanAdmin)


# Monkeypatch Organization to support Wagtail autocomplete
def org_autocomplete_label(self):
    return self.distinct_name


Organization.autocomplete_search_field = 'distinct_name'
Organization.autocomplete_label = org_autocomplete_label
