import json
import logging
from datetime import timedelta

from django import forms
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import (
    get_language, gettext, gettext_lazy as _
)
from wagtail.admin.edit_handlers import (
    FieldPanel, InlinePanel, MultiFieldPanel, ObjectList, RichTextFieldPanel
)
from wagtail.admin.forms.models import WagtailAdminModelForm
from wagtail.admin.widgets import AdminAutoHeightTextInput
from wagtail.contrib.modeladmin.options import modeladmin_register
from wagtail.images.edit_handlers import ImageChooserPanel

import humanize
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
    PlanRelatedPermissionHelper, PersistIndexViewFiltersMixin, insert_model_translation_panels, get_translation_tabs
)
from actions.chooser import ActionChooser
from actions.models import ActionResponsibleParty
from aplans.types import WatchAdminRequest
from orgs.models import Organization
from people.chooser import PersonChooser
from people.models import Person

from .attribute_type_admin import get_attribute_fields
from .models import Action, ActionTask, AttributeRichText, AttributeType, CategoryType

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

        # TODO: Refactor duplicated code (category_admin.py)
        for attribute_type, fields in get_action_attribute_fields(plan, obj):
            vals = {}
            for form_field_name, (field, model_field_name) in fields.items():
                val = self.cleaned_data.get(form_field_name)
                vals[model_field_name] = val
            attribute_type.set_value(obj, vals)
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

        # TODO: Refactor duplicated code (category_admin.py)
        if self.instance is not None:
            attribute_fields_list = get_action_attribute_fields(plan, self.instance, with_initial=True)
            attribute_fields = {form_field_name: field
                                for _, fields in attribute_fields_list
                                for form_field_name, (field, _) in fields.items()}
        else:
            attribute_fields = {}

        self.base_form_class = type(
            'ActionAdminForm',
            (ActionAdminForm,),
            {**cat_fields, **attribute_fields}
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
                default_org = plan.get_related_organizations().filter(id=person.organization_id).first()
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

        org_choices = [(str(org.id), str(org)) for org in plan.get_related_organizations()]
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


def get_action_attribute_fields(plan, action, **kwargs):
    action_ct = ContentType.objects.get_for_model(Action)
    plan_ct = ContentType.objects.get_for_model(plan)
    attribute_types = AttributeType.objects.filter(
        object_content_type=action_ct,
        scope_content_type=plan_ct,
        scope_id=plan.id,
    )
    return get_attribute_fields(attribute_types, action, **kwargs)


class AttributeFieldPanel(FieldPanel):
    def on_form_bound(self):
        super().on_form_bound()
        plan = self.request.user.get_active_admin_plan()
        attribute_fields_list = get_action_attribute_fields(plan, self.instance, with_initial=True)
        attribute_fields = {form_field_name: field
                            for _, fields in attribute_fields_list
                            for form_field_name, (field, _) in fields.items()}
        self.form.fields[self.field_name].initial = attribute_fields[self.field_name].initial


@modeladmin_register
class ActionAdmin(OrderableMixin, AplansModelAdmin):
    model = Action
    create_view_class = ActionCreateView
    index_view_class = ActionIndexView
    menu_icon = 'fa-cubes'  # change as required
    menu_label = _('Actions')
    menu_order = 1
    list_display = ('identifier', 'name_link')
    list_display_add_buttons = 'name_link'
    search_fields = ('identifier', 'name')
    permission_helper_class = ActionPermissionHelper
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
    internal_panels = [
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
        now = timezone.now()
        if not obj.updated_at:
            return None
        delta = now - obj.updated_at
        return humanize.naturaltime(delta)
    updated_at_delta.short_description = _('Last updated')

    def get_list_display(self, request: WatchAdminRequest):
        cached_list_display = getattr(request, '_action_admin_list_display', None)
        if cached_list_display:
            return cached_list_display

        try:
            humanize.activate(get_language())
        except FileNotFoundError as e:
            logger.warning(e)

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

        # TODO: Refactor duplicated code (category_admin.py)
        if instance:
            attribute_fields = get_action_attribute_fields(plan, instance, with_initial=True)
        else:
            attribute_fields = []

        for attribute_type, fields in attribute_fields:
            for form_field_name, (field, model_field_name) in fields.items():
                if len(fields) > 1:
                    heading = f'{attribute_type.name} ({model_field_name})'
                else:
                    heading = attribute_type.name
                panels.append(AttributeFieldPanel(form_field_name, heading=heading))

        if is_general_admin:
            cat_fields = _get_category_fields(instance.plan, Action, instance, with_initial=True)
            cat_panels = []
            for key, field in cat_fields.items():
                cat_panels.append(CategoryFieldPanel(key, heading=field.label))
            if cat_panels:
                panels.append(MultiFieldPanel(cat_panels, heading=_('Categories')))

        for panel in self.basic_related_panels:
            panels.append(panel)

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
                    panels=[FieldPanel('organization', widget=autocomplete.ModelSelect2(url='organization-autocomplete'))]
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

        internal_panels = list(self.internal_panels)

        if is_general_admin:
            internal_panels.append(
                FieldPanel('internal_admin_notes', widget=AdminAutoHeightTextInput(attrs=dict(rows=5)))
            )
            if plan.action_impacts.exists():
                internal_panels.append(PlanFilteredFieldPanel('impact'))
            if plan.action_schedules.exists():
                internal_panels.append(PlanFilteredFieldPanel('schedule'))

        all_tabs.append(ObjectList(internal_panels, heading=_('Internal information')))

        i18n_tabs = get_translation_tabs(instance, request)
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
