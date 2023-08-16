import json
import logging
from dal import autocomplete, forward as dal_forward

from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.urls import re_path
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from wagtail.admin.panels import (
    FieldPanel, InlinePanel, MultiFieldPanel, ObjectList
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.admin.widgets import AdminAutoHeightTextInput
from wagtail.contrib.modeladmin.options import ModelAdminMenuItem
from wagtail.contrib.modeladmin.views import IndexView

from admin_site.wagtail import (
    AplansEditView, AdminOnlyPanel, AplansButtonHelper, AplansCreateView, AplansModelAdmin, AplansTabbedInterface, CondensedInlinePanel,
    CondensedPanelSingleSelect, PlanFilteredFieldPanel, PlanRelatedPermissionHelper, insert_model_translation_panels,
    get_translation_tabs
)
from actions.chooser import ActionChooser
from aplans.extensions import modeladmin_register
from aplans.context_vars import ctx_instance, ctx_request
from aplans.types import WatchAdminRequest
from aplans.utils import naturaltime
from aplans.wagtail_utils import _get_category_fields, CategoryFieldPanel
from orgs.models import Organization
from people.chooser import PersonChooser

from .models import Action, ActionTask
from reports.views import MarkActionAsCompleteView

logger = logging.getLogger(__name__)


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

        return user.is_general_admin_for_plan(plan)

    def user_can_create(self, user):
        if not super().user_can_create(user):
            return False

        plan = user.get_active_admin_plan()
        return user.can_create_action(plan)


class ActionAdminForm(WagtailAdminModelForm):
    def clean_identifier(self):
        # Since we hide the plan in the form, `validate_unique()` will be called with `exclude` containing `plan`, in
        # which case the unique_together constraints of Action will not be checked. We do it manually here.
        identifier = self.cleaned_data['identifier']
        plan = self.instance.plan
        if Action.objects.filter(plan=plan, identifier=identifier).exclude(pk=self.instance.pk).exists():
            raise ValidationError(_("There is already an action with this identifier."))
        return identifier

    def save(self, commit=True):
        if hasattr(self.instance, 'updated_at'):
            self.instance.updated_at = timezone.now()

        obj = super().save(commit)

        # Update categories
        plan = obj.plan
        for field_name, field in _get_category_fields(plan, Action, obj).items():
            field_data = self.cleaned_data.get(field_name)
            if field_data is None:
                continue
            cat_type = field.category_type
            obj.set_categories(cat_type, field_data)

        user = self._user
        attribute_types = obj.get_editable_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.set_attributes(obj, self.cleaned_data)
        return obj


class ActionEditHandler(AplansTabbedInterface):
    def get_form_class(self):
        request = ctx_request.get()
        instance = ctx_instance.get()
        user = request.user
        plan = request.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            cat_fields = _get_category_fields(plan, Action, instance, with_initial=True)
        else:
            cat_fields = {}

        if instance is not None:
            attribute_types = instance.get_editable_attribute_types(user)
            attribute_fields = {field.name: field.django_field
                                for attribute_type in attribute_types
                                for field in attribute_type.get_form_fields(instance)}
        else:
            attribute_fields = {}

        self.base_form_class = type(
            'ActionAdminForm',
            (ActionAdminForm,),
            {**cat_fields, **attribute_fields, '_user': user}
        )

        form_class = super().get_form_class()

        if not plan.features.has_action_identifiers or plan.actions_locked:
            form_class.base_fields['identifier'].disabled = True
            form_class.base_fields['identifier'].required = False

        if plan.actions_locked and 'official_name' in form_class.base_fields:
            # 'official_name' may not be in the fields if the plan has official names disabled
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


class ActionCreateView(AplansCreateView):
    instance: Action

    def initialize_instance(self, request):
        plan = request.user.get_active_admin_plan()
        assert self.instance.pk is None
        assert not hasattr(self.instance, 'plan')
        self.instance.plan = plan
        if not plan.features.has_action_identifiers:
            assert not self.instance.identifier
            self.instance.generate_identifier()
        if plan.features.has_action_primary_orgs:
            assert self.instance.primary_org is None
            person = request.user.get_corresponding_person()
            if person is not None:
                available_orgs = Organization.objects.available_for_plan(plan)
                default_org = available_orgs.filter(id=person.organization_id).first()
                self.instance.primary_org = default_org


class ActionIndexView(IndexView):
    def get_page_title(self):
        plan = self.request.user.get_active_admin_plan()
        return plan.general_content.get_action_term_display_plural()


class ActionMenuItem(ModelAdminMenuItem):
    def render_component(self, request):
        link_menu_item = super().render_component(request)
        plan = request.user.get_active_admin_plan()
        # Change label to the configured term for "Action"
        link_menu_item.label = plan.general_content.get_action_term_display_plural()
        return link_menu_item


class ActionButtonHelper(AplansButtonHelper):
    mark_as_complete_button_classnames = []

    def mark_as_complete_button(self, action_pk, report, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.mark_as_complete_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('mark_action_as_complete', quote(action_pk), quote(report.pk)),
            'label': _("Mark as complete for report %s") % report.name,
            'classname': cn,
            'title': _("Mark this action as complete for the report %s") % str(report),
        }

    def undo_marking_as_complete_button(self, action_pk, report, **kwargs):
        classnames_add = kwargs.get('classnames_add', [])
        classnames_exclude = kwargs.get('classnames_exclude', [])
        classnames = self.mark_as_complete_button_classnames + classnames_add
        cn = self.finalise_classname(classnames, classnames_exclude)
        return {
            'url': self.url_helper.get_action_url('undo_marking_action_as_complete', quote(action_pk), quote(report.pk)),
            'label': _("Undo marking as complete for report %s") % report.name,
            'classname': cn,
            'title': _("Undo marking this action as complete for the report %s") % str(report),
        }

    def get_buttons_for_obj(self, obj, *args, **kwargs):
        buttons = super().get_buttons_for_obj(obj, *args, **kwargs)
        if self.permission_helper.user_can_edit_obj(self.request.user, obj):
            # For each report type, display one button for the latest report of that type
            for report_type in obj.plan.report_types.all():
                latest_report = report_type.reports.last()
                if latest_report and not latest_report.is_complete:
                    if obj.is_complete_for_report(latest_report):
                        buttons.append(self.undo_marking_as_complete_button(obj.pk, latest_report, **kwargs))
                    else:
                        buttons.append(self.mark_as_complete_button(obj.pk, latest_report, **kwargs))
        return buttons


class ActionEditView(AplansEditView):
    def get_description(self):
        action = self.instance
        primary_action_classification = action.plan.primary_action_classification
        if primary_action_classification is None:
            return ''
        category = action.categories.filter(type=primary_action_classification)
        if not category:
            return ''
        return str(category.first())


@modeladmin_register
class ActionAdmin(AplansModelAdmin):
    model = Action
    create_view_class = ActionCreateView
    index_view_class = ActionIndexView
    edit_view_class = ActionEditView
    menu_icon = 'kausal-action'
    menu_order = 10
    list_display = ('identifier', 'name_link')
    list_display_add_buttons = 'name_link'
    search_fields = ('identifier', 'name')
    permission_helper_class = ActionPermissionHelper
    button_helper_class = ActionButtonHelper
    index_order_field = 'order'

    ordering = ['order']

    basic_panels = [
        FieldPanel('identifier'),
        FieldPanel('official_name'),
        FieldPanel('name'),
        FieldPanel('primary_org', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        FieldPanel('lead_paragraph'),
        FieldPanel('description'),
    ]
    basic_related_panels = [
        FieldPanel('image'),
        CondensedInlinePanel(
            'links',
            panels=[
                FieldPanel('url'),
                FieldPanel('title')
            ],
            heading=_('External links')
        ),
    ]
    basic_related_panels_general_admin = [
        FieldPanel(
            'related_actions',
            widget=autocomplete.ModelSelect2Multiple(
                url='action-autocomplete',
                forward=(
                    dal_forward.Const(True, 'related_plans'),
                )
            )
        ),
        FieldPanel('merged_with', widget=ActionChooser),
        FieldPanel('visibility'),
    ]

    progress_panels = [
        PlanFilteredFieldPanel('implementation_phase'),
        PlanFilteredFieldPanel('status'),
        FieldPanel('manual_status'),
        FieldPanel('manual_status_reason'),
        FieldPanel('schedule_continuous'),
        FieldPanel('start_date'),
        FieldPanel('end_date'),
    ]
    reporting_panels = [
        FieldPanel('internal_notes', widget=AdminAutoHeightTextInput(attrs=dict(rows=5))),
    ]

    task_panels = [
        FieldPanel('name'),
        FieldPanel('due_at'),
        FieldPanel('state', widget=CondensedPanelSingleSelect),
        FieldPanel('completed_at'),
        FieldPanel('comment'),
    ]

    task_header_from_js = '''
        function getHeader(task) {
            var f = task.fields;
            var out = '';
            if (!f.name) {
                return '';
            }
            var stateMap = %(state_map)s;
            if (f.name && f.name.length > 80) {
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
        getHeader(form);
    '''

    def updated_at_delta(self, obj):
        if not obj.updated_at:
            return None
        now = obj.plan.now_in_local_timezone()
        delta = now - obj.updated_at
        return naturaltime(delta)
    updated_at_delta.short_description = _('Last updated')

    def get_list_display(self, request: WatchAdminRequest):
        cached_list_display = getattr(request, '_action_admin_list_display', None)
        if cached_list_display:
            return cached_list_display

        def name_link(obj):
            from django.utils.html import format_html

            if self.permission_helper.user_can_edit_obj(request.user, obj):
                url = self.url_helper.get_action_url('edit', obj.pk)
                return format_html('<a href="{}">{}</a>', url, obj.name)
            else:
                return obj.name
        name_link.short_description = _('Name')
        self.name_link = name_link

        plan = request.user.get_active_admin_plan()

        list_display = ['name_link']
        if plan.features.has_action_identifiers:
            list_display.insert(0, 'identifier')
        if plan.features.has_action_primary_orgs:
            list_display.insert(0, 'primary_org')

        ct = plan.category_types.filter(identifier='action').first()
        if ct:
            def action_category(obj):
                return '; '.join([str(cat) for cat in obj.categories.all() if cat.type_id == ct.id])
            action_category.short_description = ct.name
            self.action_category = action_category
            list_display.append('action_category')

        list_display.append('updated_at_delta')

        """
        if not plan.actions_locked and request.user.is_general_admin_for_plan(plan):
            list_display.insert(0, 'index_order')
        """

        out = tuple(list_display)
        request._action_admin_list_display = out
        return out

    def get_task_header_formatter(self):
        states = {key: str(label) for key, label in list(ActionTask.STATES)}
        out = self.task_header_from_js % dict(state_map=json.dumps(states))
        return out

    def get_edit_handler(self):
        request = ctx_request.get()
        instance = ctx_instance.get()
        plan = request.user.get_active_admin_plan()
        task_panels = insert_model_translation_panels(ActionTask, self.task_panels, request, plan)
        attribute_panels = instance.get_attribute_panels(request.user)
        main_attribute_panels, reporting_attribute_panels, i18n_attribute_panels = attribute_panels

        all_tabs = []

        is_general_admin = request.user.is_general_admin_for_plan(plan)
        panels = list(self.basic_panels)
        for panel in list(panels):
            field_name = getattr(panel, 'field_name', None)
            if not field_name:
                continue
            if field_name == 'official_name' and not plan.features.has_action_official_name:
                panels.remove(panel)
            elif field_name == 'lead_paragraph' and not plan.features.has_action_lead_paragraph:
                panels.remove(panel)
            elif field_name == 'primary_org' and not plan.features.has_action_primary_orgs:
                panels.remove(panel)

        panels += main_attribute_panels

        if is_general_admin:
            cat_fields = _get_category_fields(instance.plan, Action, instance, with_initial=True)
            cat_panels = []
            for key, field in cat_fields.items():
                cat_panels.append(CategoryFieldPanel(key, heading=field.label))
            if cat_panels:
                panels.append(MultiFieldPanel(cat_panels, heading=_('Categories')))

        for panel in self.basic_related_panels:
            panels.append(panel)

        if is_general_admin:
            panels += self.basic_related_panels_general_admin

            if plan.superseded_by:
                panels.append(FieldPanel('superseded_by', widget=autocomplete.ModelSelect2(
                    url='action-autocomplete',
                    forward=(
                        dal_forward.Const(plan.superseded_by.id, 'plan'),
                    )
                )))

        all_tabs.append(ObjectList(panels, heading=_('Basic information')))

        progress_panels = list(self.progress_panels)

        # If all of the action statuses are updated manually, remove the
        # manual status toggle.
        if plan.statuses_updated_manually:
            for panel in progress_panels:
                if panel.field_name == 'manual_status':
                    progress_panels.remove(panel)
                    break

        all_tabs.append(ObjectList(progress_panels, heading=_('Progress')))

        all_tabs += [
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
                    heading=_('Responsible parties'),
                    panels=[
                        FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
                        FieldPanel('role'),
                        FieldPanel('specifier'),
                    ]
                )
            ], heading=_('Responsible parties')),
            ObjectList([
                CondensedInlinePanel(
                    'tasks',
                    panels=task_panels,
                )
            ], heading=_('Tasks')),
        ]

        reporting_panels = reporting_attribute_panels
        help_panels_for_field = {}
        for snapshot in instance.get_snapshots():
            for field in snapshot.report.fields:
                help_panel = field.block.get_help_panel(field.value, snapshot)
                if help_panel:
                    help_panels_for_field.setdefault(field.id, []).append(help_panel)
        for help_panels in help_panels_for_field.values():
            reporting_panels += help_panels
        reporting_panels += list(self.reporting_panels)

        if is_general_admin:
            reporting_panels.append(
                FieldPanel('internal_admin_notes', widget=AdminAutoHeightTextInput(attrs=dict(rows=5)))
            )
            if plan.action_impacts.exists():
                reporting_panels.append(PlanFilteredFieldPanel('impact'))
            if plan.action_schedules.exists():
                reporting_panels.append(PlanFilteredFieldPanel('schedule'))

        all_tabs.append(ObjectList(reporting_panels, heading=_('Reporting')))

        i18n_tabs = get_translation_tabs(instance, request, extra_panels=i18n_attribute_panels)
        all_tabs += i18n_tabs

        return ActionEditHandler(all_tabs)

    def get_queryset(self, request):
        qs = super().get_queryset(request)
        plan = request.user.get_active_admin_plan()
        if not request.user.is_general_admin_for_plan(plan):
            qs = qs.unmerged()
        qs = qs.filter(plan=plan)
        qs = qs.select_related('plan').prefetch_related('categories')
        return qs

    def get_menu_item(self, order=None):
        return ActionMenuItem(self, order or self.get_menu_order())

    def mark_action_as_complete_view(self, request, action_pk, report_pk):
        return MarkActionAsCompleteView.as_view(
            model_admin=self,
            action_pk=action_pk,
            report_pk=report_pk,
            complete=True,
        )(request)

    def undo_marking_action_as_complete_view(self, request, action_pk, report_pk):
        return MarkActionAsCompleteView.as_view(
            model_admin=self,
            action_pk=action_pk,
            report_pk=report_pk,
            complete=False,
        )(request)

    def get_admin_urls_for_registration(self):
        urls = super().get_admin_urls_for_registration()
        mark_as_complete_url = re_path(
            # self.url_helper.get_action_url_pattern('mark_action_as_complete'),
            r'^%s/%s/%s/(?P<action_pk>[-\w]+)/(?P<report_pk>[-\w]+)/$' % (
                self.opts.app_label,
                self.opts.model_name,
                'mark_action_as_complete',
            ),
            self.mark_action_as_complete_view,
            name=self.url_helper.get_action_url_name('mark_action_as_complete')
        )
        undo_marking_as_complete_url = re_path(
            # self.url_helper.get_action_url_pattern('undo_marking_action_as_complete'),
            r'^%s/%s/%s/(?P<action_pk>[-\w]+)/(?P<report_pk>[-\w]+)/$' % (
                self.opts.app_label,
                self.opts.model_name,
                'undo_marking_action_as_complete',
            ),
            self.undo_marking_action_as_complete_view,
            name=self.url_helper.get_action_url_name('undo_marking_action_as_complete')
        )
        return urls + (
            mark_as_complete_url,
            undo_marking_as_complete_url,
        )
