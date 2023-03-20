import json
import logging
from datetime import timedelta

from django import forms
from django.contrib.admin.utils import quote
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.urls import re_path
from django.utils import timezone
from django.utils.translation import gettext, gettext_lazy as _
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, MultiFieldPanel, ObjectList, RichTextFieldPanel
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.admin.widgets import AdminAutoHeightTextInput
from wagtail.contrib.modeladmin.helpers import ButtonHelper
from wagtail.images.edit_handlers import ImageChooserPanel

from admin_list_controls.actions import SubmitForm, TogglePanel
from admin_list_controls.components import (
    Block, Button, Columns, Icon, Panel, Spacer, Summary
)
from admin_list_controls.filters import ChoiceFilter, RadioFilter
from admin_list_controls.views import ListControlsIndexView

from dal import autocomplete, forward as dal_forward
from wagtailorderable.modeladmin.mixins import OrderableMixin

from admin_site.wagtail import (
    AdminOnlyPanel, AplansCreateView, AplansModelAdmin, AplansTabbedInterface,
    CondensedInlinePanel, CondensedPanelSingleSelect, PlanFilteredFieldPanel,
    PlanRelatedPermissionHelper, PersistIndexViewFiltersMixin, SafeLabelModelAdminMenuItem,
    insert_model_translation_panels, get_translation_tabs
)
from actions.chooser import ActionChooser
from actions.models import ActionResponsibleParty
from aplans.types import WatchAdminRequest
from aplans.utils import naturaltime
from aplans.extensions import modeladmin_register
from orgs.models import Organization
from people.chooser import PersonChooser
from people.models import Person

from .models import Action, ActionTask, CategoryType
from reports.views import MarkActionAsCompleteView

logger = logging.getLogger(__name__)


class ModelChoiceFieldWithValueInList(forms.ModelChoiceField):
    """Like ModelMultipleChoiceField, but allow only one value to be chosen."""
    def to_python(self, value):
        result = super().to_python(value)
        if not result:
            return []
        return [result]

    def prepare_value(self, value):
        if (hasattr(value, '__iter__') and
                not isinstance(value, str) and
                not hasattr(value, '_meta')):
            prepare_value = super().prepare_value
            return [prepare_value(v) for v in value]
        return super().prepare_value(value)


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
        if obj and obj.pk and with_initial:
            initial = obj.categories.filter(type=cat_type)
        else:
            initial = None
        field_class = forms.ModelMultipleChoiceField
        if cat_type.select_widget == CategoryType.SelectWidget.SINGLE:
            field_class = ModelChoiceFieldWithValueInList

            widget = autocomplete.ModelSelect2(
                url='category-autocomplete',
                forward=(
                    dal_forward.Const(cat_type.id, 'type'),
                )
            )
        else:
            field_class = forms.ModelMultipleChoiceField
            widget = autocomplete.ModelSelect2Multiple(
                url='category-autocomplete',
                forward=(
                    dal_forward.Const(cat_type.id, 'type'),
                )
            )
        field = field_class(
            qs, label=cat_type.name, initial=initial, required=False, widget=widget
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
    instance: Action

    def get_form_class(self, request: WatchAdminRequest = None):
        assert request is not None
        user = request.user
        plan = request.get_active_admin_plan()
        if user.is_general_admin_for_plan(plan):
            cat_fields = _get_category_fields(plan, Action, self.instance, with_initial=True)
        else:
            cat_fields = {}

        if self.instance is not None:
            attribute_types = self.instance.get_editable_attribute_types(user)
            attribute_fields = {field.name: field.django_field
                                for attribute_type in attribute_types
                                for field in attribute_type.get_form_fields(self.instance)}
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

        if plan.actions_locked:
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
    def get_instance(self) -> Action:
        # Override default implementation, which would try to create an
        # instance of self.model (i.e., Action) without a plan, causing an
        # error when saving it
        instance: Action = super().get_instance()
        if instance.pk:
            return instance

        plan = self.request.get_active_admin_plan()
        instance.plan = plan
        if not instance.identifier and not plan.features.has_action_identifiers:
            instance.generate_identifier()
        if plan.features.has_action_primary_orgs:
            person = self.request.user.get_corresponding_person()
            if person is not None:
                available_orgs = Organization.objects.available_for_plan(plan)
                default_org = available_orgs.filter(id=person.organization_id).first()
                instance.primary_org = default_org

        return instance


class ActionIndexView(PersistIndexViewFiltersMixin, ListControlsIndexView):
    def filter_by_person(self, queryset, value):
        if not value:
            return queryset

        person = Person.objects.filter(id=value).first()
        if person is not None:
            qs = queryset.filter(contact_persons__person=person).distinct()
            return qs
        else:
            return queryset.none()

    def filter_by_organization(self, queryset, value):
        try:
            org = Organization.objects.get(id=value)
        except Organization.DoesNotExist:
            return queryset.none()
        orgs = Organization.objects.filter(id=org.id) | org.get_descendants()
        responsibilities = ActionResponsibleParty.objects.filter(organization__in=orgs).values_list('action', flat=True)
        return queryset.filter(Q(primary_org__in=orgs) | Q(id__in=responsibilities))

    def create_cat_filters(self, plan):
        ct_filters = []
        for ct in plan.category_types.filter(usable_for_actions=True).all():
            def filter_by_cat(queryset, value):
                if not value:
                    return queryset

                cat_with_kittens = set()

                def add_cat(cat):
                    cat_with_kittens.add(cat)
                    for kitten in cat.children.all():
                        add_cat(kitten)

                cat = ct.categories.filter(id=value).first()
                if not cat:
                    return queryset.none()
                add_cat(cat)
                return queryset.filter(categories__in=cat_with_kittens).distinct()

            choices = []

            def add_cat_recursive(cat, level):
                if cat.identifier[0].isdigit():
                    id_str = '%s. ' % cat.identifier
                else:
                    id_str = ''
                choice = (str(cat.id), '%s%s%s' % (' ' * level, id_str, cat.name))
                choices.append(choice)
                for child in cat.children.all():
                    add_cat_recursive(child, level + 1)

            for cat in ct.categories.filter(parent=None):
                add_cat_recursive(cat, 0)

            ct_filters.append(ChoiceFilter(
                name='category_%s' % ct.identifier,
                label=ct.name,
                choices=choices,
                apply_to_queryset=filter_by_cat,
            ))
        return ct_filters

    def filter_own_action(self, queryset, value):
        user = self.request.user
        if value == 'modifiable':
            return queryset.modifiable_by(user)
        elif value == 'contact_person':
            person = user.get_corresponding_person()
            if person is None:
                return queryset.none()
            else:
                return queryset.filter(contact_persons__person=person)
        return queryset

    def filter_last_updated(self, queryset, value):
        if not value:
            return queryset

        start = end = None
        if value.endswith('-'):
            start = value.strip('-')
        elif value.startswith('-'):
            end = value.strip('-')
        else:
            start, end = value.split('-')

        now = timezone.now()
        if start:
            queryset = queryset.filter(updated_at__lte=now - timedelta(days=int(start)))
        if end:
            queryset = queryset.filter(updated_at__gte=now - timedelta(days=int(end)))
        return queryset

    def build_list_controls(self):
        user = self.request.user
        plan = user.get_active_admin_plan()

        qs = Person.objects.filter(contact_for_actions__plan=plan).distinct()
        person_choices = [(str(person.id), str(person)) for person in qs]
        person_filter = ChoiceFilter(
            name='contact_person',
            label=gettext('Contact person'),
            choices=person_choices,
            apply_to_queryset=self.filter_by_person,
        )
        ct_filters = self.create_cat_filters(plan)

        org_choices = [(str(org.id), str(org)) for org in Organization.objects.available_for_plan(plan)]
        org_filter = ChoiceFilter(
            name='organization',
            label=gettext('Organization'),
            choices=org_choices,
            apply_to_queryset=self.filter_by_organization,
        )

        own_actions = RadioFilter(
            name='own',
            label=gettext('Own actions'),
            choices=[
                ('contact_person', gettext('Show only actions with me as a contact person')),
                ('modifiable', gettext('Show only actions I can modify')),
                (None, gettext('Show all actions')),
            ],
            apply_to_queryset=self.filter_own_action
        )

        updated_filter = RadioFilter(
            name='last_updated',
            label=gettext('By last updated'),
            choices=[
                (None, gettext('No filtering')),
                ('-7', gettext('In the last 7 days')),
                ('7-30', gettext('7–30 days ago')),
                ('30-120', gettext('1–3 months ago')),
                ('120-', gettext('More than 3 months ago')),
            ],
            apply_to_queryset=self.filter_last_updated,
        )

        return [
            Columns(column_count=2)(
                Block(extra_classes='own-action-filter')(own_actions),
                Block(extra_classes='own-action-filter')(org_filter)
            ),
            Button(action=SubmitForm())(
                Icon('icon icon-tick'),
                gettext("Apply filters"),
            ),
            Button(action=[
                TogglePanel(ref='filter_panel'),
            ])(Icon('icon icon-list-ul'), gettext('Advanced filters')),
            Panel(ref='filter_panel', collapsed=True)(
                Columns()(person_filter),
                Columns()(*ct_filters),
                Spacer(),
                Spacer(),
                updated_filter,
            ),
            Summary(reset_label=gettext('Reset all'), search_query_label=gettext('Search')),
        ]

    def get_page_title(self):
        plan = self.request.user.get_active_admin_plan()
        return plan.general_content.get_action_term_display_plural()


class ActionMenuItem(SafeLabelModelAdminMenuItem):
    def get_label_from_context(self, context, request):
        # Ignore context; the label is going to be the configured term for "Action"
        plan = request.user.get_active_admin_plan()
        return plan.general_content.get_action_term_display_plural()


class ActionButtonHelper(ButtonHelper):
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
        # For each report type, display one button for the latest report of that type
        for report_type in obj.plan.report_types.all():
            latest_report = report_type.reports.last()
            if latest_report and not latest_report.is_complete:
                if obj.is_complete_for_report(latest_report):
                    buttons.append(self.undo_marking_as_complete_button(obj.pk, latest_report, **kwargs))
                else:
                    buttons.append(self.mark_as_complete_button(obj.pk, latest_report, **kwargs))
        return buttons



@modeladmin_register
class ActionAdmin(OrderableMixin, AplansModelAdmin):
    model = Action
    create_view_class = ActionCreateView
    index_view_class = ActionIndexView
    menu_icon = 'fa-cubes'  # change as required
    menu_order = 1
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
        FieldPanel('name', classname='full title'),
        FieldPanel('primary_org', widget=autocomplete.ModelSelect2(url='organization-autocomplete')),
        FieldPanel('lead_paragraph'),
        RichTextFieldPanel('description'),
    ]
    basic_related_panels = [
        ImageChooserPanel('image'),
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
        RichTextFieldPanel('comment'),
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

        if not plan.actions_locked and request.user.is_general_admin_for_plan(plan):
            list_display.insert(0, 'index_order')

        out = tuple(list_display)
        request._action_admin_list_display = out
        return out

    def get_task_header_formatter(self):
        states = {key: str(label) for key, label in list(ActionTask.STATES)}
        out = self.task_header_from_js % dict(state_map=json.dumps(states))
        return out

    def get_edit_handler(self, instance: Action, request: WatchAdminRequest):
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
                    card_header_from_js_safe=self.get_task_header_formatter()
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
