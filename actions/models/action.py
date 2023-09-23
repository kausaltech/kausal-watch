from __future__ import annotations
import logging
import reversion
import typing
import uuid
from django.contrib.contenttypes.fields import GenericRelation
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import FieldDoesNotExist, ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models import IntegerField, Max, Q
from django.db.models.functions import Cast
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel, model_from_serializable_data
from modeltrans.fields import TranslationField, TranslatedVirtualField
from modeltrans.translator import get_i18n_field
from reversion.models import Version
from typing import Literal, Optional, TypedDict
from wagtail.fields import RichTextField
from wagtail.models import DraftStateMixin, LockableMixin, RevisionMixin, Task, WorkflowMixin
from wagtail.search import index
from wagtail.search.queryset import SearchableQuerySetMixin

from aplans.utils import (
    IdentifierField, OrderedModel, PlanRelatedModel, generate_identifier
)
from orgs.models import Organization
from users.models import User

from ..action_status_summary import ActionStatusSummaryIdentifier, ActionTimelinessIdentifier
from ..attributes import AttributeType
from ..monitoring_quality import determine_monitoring_quality
from .attributes import AttributeType as AttributeTypeModel, ModelWithAttributes

if typing.TYPE_CHECKING:
    from .plan import Plan
    from django.db.models.manager import RelatedManager


logger = logging.getLogger(__name__)


class ActionQuerySet(SearchableQuerySetMixin, models.QuerySet):
    def modifiable_by(self, user: User):
        if user.is_superuser:
            return self
        person = user.get_corresponding_person()
        query = Q(responsible_parties__organization__in=user.get_adminable_organizations())
        if person:
            query |= Q(plan__in=person.general_admin_plans.all())
            query |= Q(contact_persons__person=person)
        return self.filter(query).distinct()

    def user_is_contact_for(self, user: User):
        person = user.get_corresponding_person()
        if person is None:
            return self.none()
        qs = self.filter(Q(contact_persons__person=person)).distinct()
        return qs

    def user_is_org_admin_for(self, user: User, plan: Optional[Plan] = None):
        plan_admin_orgs = Organization.objects.user_is_plan_admin_for(user, plan)
        query = Q(responsible_parties__organization__in=plan_admin_orgs) | Q(primary_org__in=plan_admin_orgs)
        return self.filter(query).distinct()

    def user_has_staff_role_for(self, user: User, plan: Optional[Plan] = None):
        qs = self.user_is_contact_for(user) | self.user_is_org_admin_for(user, plan)
        return qs

    def unmerged(self):
        return self.filter(merged_with__isnull=True)

    def active(self):
        return self.unmerged().exclude(status__is_completed=True)

    def visible_for_user(self, user: Optional[User], plan: Optional[Plan] = None):
        """ A None value is interpreted identically
        to a non-authenticated user"""
        if user is None or not user.is_authenticated:
            return self.filter(visibility=DraftableModel.VisibilityState.PUBLIC)
        return self

    def complete_for_report(self, report):
        from reports.models import ActionSnapshot
        action_ids = (
            ActionSnapshot.objects.filter(report=report)
            .annotate(action_id=Cast('action_version__object_id', output_field=IntegerField()))
            .values_list('action_id')
        )
        return self.filter(id__in=action_ids)


class ActionIdentifierSearchMixin:
    def get_value(self, obj: Action):
        # If the plan doesn't have meaningful action identifiers,
        # do not index them.
        if not obj.plan.features.has_action_identifiers:
            return None
        return super().get_value(obj)


class ActionIdentifierSearchField(ActionIdentifierSearchMixin, index.SearchField):
    pass


class ActionIdentifierAutocompleteField(ActionIdentifierSearchMixin, index.AutocompleteField):
    pass


class ResponsiblePartyDict(TypedDict):
    organization: Organization
    # Allowed roles in ActionResponsibleParty.Role.values
    # https://stackoverflow.com/a/67292548/14595546
    role: Literal['primary', 'collaborator', None]


class DraftableModel(models.Model):
    class VisibilityState(models.TextChoices):
        DRAFT = 'draft', _('Draft')
        PUBLIC = 'public', _('Public')

    visibility = models.CharField(
        blank=False, null=False,
        default=VisibilityState.PUBLIC,
        choices=VisibilityState.choices,
        max_length=20,
        verbose_name=_('visibility'),
    )

    class Meta:
        abstract = True


@reversion.register(follow=ModelWithAttributes.REVERSION_FOLLOW + ['responsible_parties'])
class Action(
    WorkflowMixin, DraftStateMixin, LockableMixin, RevisionMixin,
    ModelWithAttributes, OrderedModel, ClusterableModel, PlanRelatedModel, DraftableModel, index.Indexed
):
    """One action/measure tracked in an action plan."""

    def revision_enabled(self):
        return self.plan.features.enable_moderation_workflow

    def save_revision(self, *args, **kwargs):
        # This method has been overridden temporarily.
        #
        # The reason is that for plans without the moderation workflow enabled, RevisionMixin.save_revision is still called for all
        # subclasses of RevisionMixin.
        #
        # This results in newly created actions to have has_unpublished_changes == True and a revision to be created for them. This in turn
        # results in the action edit form not showing the actual saved action data but the data of a "draft" revision (which itself cannot
        # be edited in a plan with workflows disabled currently).
        #
        # In the future we will probably want to have drafting enabled by default for all plans and we can remove this.
        if not self.revision_enabled():
            return None
        return super().save_revision(*args, **kwargs)

    def commit_attributes(self, attributes, user):
        """Called when the serialized draft contents of attribute values must be persisted to the actual Attribute models
        when publishing an action from a draft"""
        attribute_types = self.get_visible_attribute_types(user)
        for attribute_type in attribute_types:
            attribute_type.commit_value_from_serialized_data(
                self, attributes
            )

    def publish(self, revision, user=None, **kwargs):
        attributes = revision.content.pop('attributes')
        super().publish(revision, user=user, **kwargs)
        self.commit_attributes(attributes, user)

    def serializable_data(self, *args, **kwargs):
        # Do not serialize translated virtual fields
        i18n_field = get_i18n_field(self)
        assert i18n_field
        for field in i18n_field.get_translated_fields():
            assert field.serialize is True
            field.serialize = False
        try:
            result = super().serializable_data(*args, **kwargs)
            result['attributes'] = self.get_serialized_attribute_data()
            return result
        finally:
            for field in i18n_field.get_translated_fields():
                field.serialize = True

    @classmethod
    def from_serializable_data(cls, data, check_fks=True, strict_fks=False):
        attribute_data = data.pop('attributes', {})
        result: Action = super().from_serializable_data(data, check_fks=check_fks, strict_fks=strict_fks)
        result.set_serialized_attribute_data(attribute_data)
        return result

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    plan: Plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='actions',
        verbose_name=_('plan')
    )
    primary_org = models.ForeignKey(
        'orgs.Organization', verbose_name=_('primary organization'),
        blank=True, null=True, on_delete=models.SET_NULL,
    )
    name = models.CharField(max_length=1000, verbose_name=_('name'))
    official_name = models.TextField(
        null=True, blank=True, verbose_name=_('official name'),
        help_text=_('The name as approved by an official party')
    )
    identifier = IdentifierField(
        help_text=_('The identifier for this action (e.g. number)')
    )
    image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
        verbose_name=_('Image')
    )
    lead_paragraph = models.TextField(blank=True, verbose_name=_('Lead paragraph'))
    description = RichTextField(
        null=True, blank=True,
        verbose_name=_('description'),
        help_text=_('What does this action involve in more detail?'))
    impact = models.ForeignKey(
        'ActionImpact', blank=True, null=True, related_name='actions', on_delete=models.SET_NULL,
        verbose_name=_('impact'), help_text=_('The impact of this action'),
    )
    internal_priority = models.PositiveIntegerField(
        blank=True, null=True, verbose_name=_('internal priority')
    )
    internal_admin_notes = models.TextField(
        blank=True, null=True, verbose_name=_('internal notes for plan administrators')
    )
    internal_notes = models.TextField(
        blank=True, null=True, verbose_name=_('internal notes')
    )
    status = models.ForeignKey(
        'ActionStatus', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('status'),
    )
    implementation_phase = models.ForeignKey(
        'ActionImplementationPhase', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('implementation phase'),
    )
    manual_status = models.BooleanField(
        default=False, verbose_name=_('override status manually'),
        help_text=_('Set if you want to prevent the action status from being determined automatically')
    )
    manual_status_reason = models.TextField(
        blank=True, null=True, verbose_name=_('specifier for status'),
        help_text=_('Describe the reason why this action has has this status')
    )

    merged_with = models.ForeignKey(
        'Action', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('merged with action'), help_text=_('Set if this action is merged with another action'),
        related_name='merged_actions'
    )
    completion = models.PositiveIntegerField(
        null=True, blank=True, verbose_name=_('completion'), editable=False,
        help_text=_('The completion percentage for this action')
    )
    schedule = models.ManyToManyField(
        'ActionSchedule', blank=True,
        verbose_name=_('schedule')
    )
    schedule_continuous = models.BooleanField(
        default=False, verbose_name=_('continuous action'),
        help_text=_('Set if the action does not have a start or an end date')
    )
    decision_level = models.ForeignKey(
        'ActionDecisionLevel', blank=True, null=True, related_name='actions', on_delete=models.SET_NULL,
        verbose_name=_('decision-making level')
    )
    categories = models.ManyToManyField(
        'Category', blank=True, verbose_name=_('categories'), related_name='actions',
    )
    indicators = models.ManyToManyField(
        'indicators.Indicator', blank=True, verbose_name=_('indicators'),
        through='indicators.ActionIndicator', related_name='actions'
    )
    related_actions = models.ManyToManyField('self', blank=True, verbose_name=_('related actions'))

    responsible_organizations = models.ManyToManyField(
        Organization, through='ActionResponsibleParty', blank=True,
        related_name='responsible_for_actions', verbose_name=_('responsible organizations')
    )

    contact_persons_unordered = models.ManyToManyField(
        'people.Person', through='ActionContactPerson', blank=True,
        related_name='contact_for_actions', verbose_name=_('contact persons')
    )

    monitoring_quality_points = models.ManyToManyField(
        'MonitoringQualityPoint', blank=True, related_name='actions',
        editable=False,
    )

    updated_at = models.DateTimeField(
        editable=False, verbose_name=_('updated at'), default=timezone.now
    )
    start_date = models.DateField(
        verbose_name=_('start date'),
        help_text=_('The date when implementation of this action starts'),
        blank=True,
        null=True,
    )
    end_date = models.DateField(
        verbose_name=_('end date'),
        help_text=_('The date when implementation of this action ends'),
        blank=True,
        null=True,
    )
    superseded_by = models.ForeignKey(
        'self', verbose_name=pgettext_lazy('action', 'superseded by'), blank=True, null=True, on_delete=models.SET_NULL,
        related_name='superseded_actions', help_text=_('Set if this action is superseded by another action')
    )

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='action')

    i18n = TranslationField(
        fields=('name', 'official_name', 'description', 'manual_status_reason'),
        default_language_field='plan__primary_language',
    )

    objects = ActionQuerySet.as_manager()

    search_fields = [
        index.SearchField('name', boost=10),
        index.AutocompleteField('name'),
        ActionIdentifierSearchField('identifier', boost=10),
        ActionIdentifierAutocompleteField('identifier'),
        index.SearchField('official_name', boost=8),
        index.AutocompleteField('official_name'),
        index.SearchField('description'),
        index.RelatedFields('tasks', [
            index.SearchField('name'),
            index.SearchField('comment'),
        ]),
        index.FilterField('plan'),
        index.FilterField('updated_at'),
        index.FilterField('visibility'),
    ]
    search_auto_update = True

    # Used by GraphQL + REST API code
    public_fields = [
        'id', 'uuid', 'plan', 'name', 'official_name', 'identifier', 'lead_paragraph', 'description', 'status',
        'completion', 'schedule', 'schedule_continuous', 'decision_level', 'responsible_parties',
        'categories', 'indicators', 'contact_persons', 'updated_at', 'start_date', 'end_date', 'tasks',
        'related_actions', 'related_indicators', 'impact', 'status_updates', 'merged_with', 'merged_actions',
        'impact_groups', 'monitoring_quality_points', 'implementation_phase', 'manual_status_reason', 'links',
        'primary_org', 'order', 'superseded_by', 'superseded_actions',
    ]

    # type annotations for related objects
    contact_persons: RelatedManager[ActionContactPerson]

    verbose_name_partitive = pgettext_lazy('partitive', 'action')

    class Meta:
        verbose_name = _('action')
        verbose_name_plural = _('actions')
        ordering = ('plan', 'order')
        index_together = (('plan', 'order'),)
        unique_together = (('plan', 'identifier'),)
        permissions = (
            ('admin_action', _("Can administrate all actions")),
        )

    MODEL_ADMIN_CLASS = 'actions.action_admin.ActionAdmin'  # for AdminButtonsMixin

    def __str__(self):
        s = ''
        if self.plan is not None and self.plan.features.has_action_identifiers:
            s += '%s. ' % self.identifier
        s += self.name
        return s

    def clean(self):
        if self.merged_with is not None:
            other = self.merged_with
            if other.merged_with == self:
                raise ValidationError({'merged_with': _('Other action is merged with this one')})
        # FIXME: Make sure FKs and M2Ms point to objects that are within the
        # same action plan.

    def save(self, *args, **kwargs):
        if self.pk is None:
            qs = self.plan.actions.values('order').order_by()
            max_order = qs.aggregate(Max('order'))['order__max']
            if max_order is None:
                self.order = 0
            else:
                self.order = max_order + 1
        return super().save(*args, **kwargs)

    def is_merged(self):
        return self.merged_with_id is not None

    def is_active(self):
        return not self.is_merged() and (self.status is None or not self.status.is_completed)

    def get_next_action(self, user: User):
        return (
            Action.objects
            .visible_for_user(user)
            .filter(plan=self.plan_id, order__gt=self.order)
            .unmerged()
            .first()
        )

    def get_previous_action(self, user: User):
        return (
            Action.objects
            .visible_for_user(user)
            .filter(plan=self.plan_id, order__lt=self.order)
            .unmerged()
            .order_by('-order')
            .first()
        )

    def _calculate_status_from_indicators(self):
        progress_indicators = self.related_indicators.filter(indicates_action_progress=True)
        total_completion = 0
        total_indicators = 0
        is_late = False

        for action_ind in progress_indicators:
            ind = action_ind.indicator
            try:
                latest_value = ind.values.latest()
            except ind.values.model.DoesNotExist:
                continue

            start_value = ind.values.first()

            try:
                last_goal = ind.goals.latest()
            except ind.goals.model.DoesNotExist:
                continue

            diff = last_goal.value - start_value.value

            if not diff:
                # Avoid divide by zero
                continue

            completion = (latest_value.value - start_value.value) / diff
            total_completion += completion
            total_indicators += 1

            # Figure out if the action is late or not by comparing
            # the latest measured value to the closest goal
            closest_goal = ind.goals.filter(date__lte=latest_value.date).last()
            if closest_goal is None:
                continue

            # Are we supposed to up or down?
            if diff > 0:
                # Up!
                if closest_goal.value - latest_value.value > 0:
                    is_late = True
            else:
                # Down
                if closest_goal.value - latest_value.value < 0:
                    is_late = True

        if not total_indicators:
            return None

        # Return average completion
        completion = int((total_completion / total_indicators) * 100)
        if completion <= 0:
            return None
        return dict(completion=completion, is_late=is_late)

    def _calculate_completion_from_tasks(self, tasks):
        if not tasks:
            return None
        n_completed = len(list(filter(lambda x: x.completed_at is not None, tasks)))
        return dict(completion=int(n_completed * 100 / len(tasks)))

    def _determine_status(self, tasks, indicator_status, today=None):
        if today is None:
            today = self.plan.now_in_local_timezone().date()

        statuses = self.plan.action_statuses.all()
        if not statuses:
            return None

        by_id = {x.identifier: x for x in statuses}
        KNOWN_IDS = {'not_started', 'on_time', 'late'}
        # If the status set is not something we can handle, bail out.
        if not KNOWN_IDS.issubset(set(by_id.keys())):
            logger.warning(
                'Unable to determine action statuses for plan %s: '
                'right statuses missing' % self.plan.identifier
            )
            return None

        if indicator_status is not None and indicator_status.get('is_late'):
            return by_id['late']

        def is_late(task):
            if task.due_at is None or task.completed_at is not None:
                return False
            return today > task.due_at

        late_tasks = list(filter(is_late, tasks))
        if not late_tasks:
            completed_tasks = list(filter(lambda x: x.completed_at is not None, tasks))
            if not completed_tasks:
                return by_id['not_started']
            else:
                return by_id['on_time']

        return by_id['late']

    def recalculate_status(self, force_update=False):
        if self.merged_with is not None or self.manual_status:
            return

        if self.status is not None and self.status.is_completed:
            if self.status.identifier == 'completed' and self.completion != 100:
                self.completion = 100
                self.save(update_fields=['completion'])
            return

        determine_monitoring_quality(self, self.plan.monitoring_quality_points.all())

        indicator_status = self._calculate_status_from_indicators()
        if indicator_status:
            new_completion = indicator_status['completion']
        else:
            new_completion = None

        if self.completion != new_completion or force_update:
            self.completion = new_completion
            self.updated_at = timezone.now()
            self.save(update_fields=['completion', 'updated_at'])

        if self.plan.statuses_updated_manually:
            return

        tasks = self.tasks.exclude(state=ActionTask.CANCELLED).only('due_at', 'completed_at')
        status = self._determine_status(tasks, indicator_status)
        if status is not None and status.id != self.status_id:
            self.status = status
            self.save(update_fields=['status'])

    def handle_admin_save(self, context: Optional[dict] = None):
        self.recalculate_status(force_update=True)

    def set_categories(self, type, categories):
        if isinstance(type, str):
            type = self.plan.category_types.get(identifier=type)
        all_cats = {x.id: x for x in type.categories.all()}

        existing_cats = set(self.categories.filter(type=type))
        new_cats = set()
        for cat in categories:
            if isinstance(cat, int):
                cat = all_cats[cat]
            new_cats.add(cat)

        for cat in existing_cats - new_cats:
            self.categories.remove(cat)
        for cat in new_cats - existing_cats:
            self.categories.add(cat)

    def set_responsible_parties(self, data: list[ResponsiblePartyDict]):
        existing_orgs = set((p.organization for p in self.responsible_parties.all()))
        new_orgs = set(d['organization'] for d in data)
        ActionResponsibleParty.objects.filter(
            action=self, organization__in=(existing_orgs - new_orgs)
        ).delete()
        for d in data:
            ActionResponsibleParty.objects.update_or_create(
                action=self,
                organization=d['organization'],
                defaults={'role': d['role']},
            )

    def set_contact_persons(self, data: list):
        existing_persons = set((p.person for p in self.contact_persons.all()))
        new_persons = set(d['person'] for d in data)
        ActionContactPerson.objects.filter(
            action=self, person__in=(existing_persons - new_persons)
        ).delete()
        for d in data:
            ActionContactPerson.objects.update_or_create(
                action=self,
                person=d['person'],
                defaults={'role': d['role']},
            )

    def generate_identifier(self):
        self.identifier = generate_identifier(self.plan.actions.all(), 'a', 'identifier')

    def get_notification_context(self, plan=None):
        if plan is None:
            plan = self.plan
        change_url = reverse('actions_action_modeladmin_edit', kwargs=dict(instance_pk=self.id))
        return {
            'id': self.id, 'identifier': self.identifier, 'name': self.name, 'change_url': change_url,
            'updated_at': self.updated_at, 'view_url': self.get_view_url(plan=plan), 'order': self.order,
        }

    def has_contact_persons(self):
        return self.contact_persons.exists()
    has_contact_persons.short_description = _('Has contact persons')
    has_contact_persons.boolean = True

    def active_task_count(self):
        def task_active(task):
            return task.state != ActionTask.CANCELLED and not task.completed_at

        active_tasks = [task for task in self.tasks.all() if task_active(task)]
        return len(active_tasks)
    active_task_count.short_description = _('Active tasks')

    def get_view_url(self, plan: Optional[Plan] = None, client_url: Optional[str] = None) -> str:
        if plan is None:
            plan = self.plan
        return '%s/actions/%s' % (plan.get_view_url(client_url=client_url), self.identifier)

    @classmethod
    def get_indexed_objects(cls):
        # Return only the actions whose plan supports the current language
        lang = translation.get_language()
        qs = super().get_indexed_objects()
        qs = qs.filter(Q(plan__primary_language__istartswith=lang) | Q(plan__other_languages__icontains=[lang]))
        # FIXME find out how to use action default manager here
        qs = qs.filter(visibility=DraftableModel.VisibilityState.PUBLIC)
        return qs

    def get_attribute_type_by_identifier(self, identifier):
        return self.plan.action_attribute_types.get(identifier=identifier)

    def get_visible_attribute_types(self, user, only_in_reporting_tab=False, unless_in_reporting_tab=False):
        return self.__class__.get_visible_attribute_types_for_plan(
            user,
            self.plan,
            only_in_reporting_tab=only_in_reporting_tab,
            unless_in_reporting_tab=unless_in_reporting_tab
        )

    @classmethod
    def get_visible_attribute_types_for_plan(cls, user, plan, only_in_reporting_tab=False, unless_in_reporting_tab=False):
        action_ct = ContentType.objects.get_for_model(Action)
        plan_ct = ContentType.objects.get_for_model(plan)
        attribute_types = AttributeTypeModel.objects.filter(
            object_content_type=action_ct,
            scope_content_type=plan_ct,
            scope_id=plan.id,
        )
        if only_in_reporting_tab:
            attribute_types = attribute_types.filter(show_in_reporting_tab=True)
        if unless_in_reporting_tab:
            attribute_types = attribute_types.filter(show_in_reporting_tab=False)
        attribute_types = (at for at in attribute_types if at.are_instances_visible_for(user, plan))
        # Convert to wrapper objects
        return [AttributeType.from_model_instance(at) for at in attribute_types]

    def get_attribute_panels(self, user, serialized_attributes=None):
        # Return a triple `(main_panels, reporting_panels, i18n_panels)`, where `main_panels` is a list of panels to be
        # put on the main tab, `reporting_panels` is a list of panels to be put on the reporting tab, and `i18n_panels`
        # is a dict mapping a non-primary language to a list of panels to be put on the tab for that language.
        main_panels = []
        reporting_panels = []
        i18n_panels = {}
        plan = user.get_active_admin_plan()  # not sure if this is reasonable...
        for panels, kwargs in [(main_panels, {'unless_in_reporting_tab': True}),
                               (reporting_panels, {'only_in_reporting_tab': True})]:
            attribute_types = self.get_visible_attribute_types(user, **kwargs)
            for attribute_type in attribute_types:
                fields = attribute_type.get_form_fields(user, plan, self, serialized_attributes=serialized_attributes)
                for field in fields:
                    if field.language:
                        i18n_panels.setdefault(field.language, []).append(field.get_panel())
                    else:
                        panels.append(field.get_panel())
        return (main_panels, reporting_panels, i18n_panels)

    def get_siblings(self, force_refresh=False):
        if force_refresh:
            del self.plan.cached_actions
        return self.plan.cached_actions

    def get_prev_sibling(self):
        all_actions = self.plan.cached_actions
        for i, sibling in enumerate(all_actions):
            if sibling.id == self.id:
                if i == 0:
                    return None
                return all_actions[i - 1]
        assert False  # should have returned above at some point

    def get_snapshots(self, report=None):
        """Return the snapshots of this action, optionally restricted to those for the given report."""
        from reports.models import ActionSnapshot
        versions = Version.objects.get_for_object(self)
        qs = ActionSnapshot.objects.filter(action_version__in=versions)
        if report is not None:
            qs = qs.filter(report=report)
        return qs

    def get_latest_snapshot(self, report=None):
        """Return the latest snapshot of this action, optionally restricted to those for the given report.

        Raises ActionSnapshot.DoesNotExist if no such snapshot exists.
        """
        return self.get_snapshots(report).latest()

    def is_complete_for_report(self, report):
        from reports.models import ActionSnapshot
        try:
            self.get_latest_snapshot(report)
        except ActionSnapshot.DoesNotExist:
            return False
        return True

    def mark_as_complete_for_report(self, report, user):
        from reports.models import ActionSnapshot
        if self.is_complete_for_report(report):
            raise ValueError(_("The action is already marked as complete for report %s.") % report)
        with reversion.create_revision():
            reversion.add_to_revision(self)
            reversion.set_comment(
                _("Marked action '%(action)s' as complete for report '%(report)s'") % {
                    'action': self, 'report': report})
            reversion.set_user(user)
        ActionSnapshot.objects.create(
            report=report,
            action=self,
        )

    def undo_marking_as_complete_for_report(self, report, user):
        from reports.models import ActionSnapshot
        snapshots = ActionSnapshot.objects.filter(
            report=report,
            action_version__in=Version.objects.get_for_object(self),
        )
        num_snapshots = snapshots.count()
        if num_snapshots != 1:
            raise ValueError(_("Cannot undo marking action as complete as there are %s snapshots") % num_snapshots)
        with reversion.create_revision():
            reversion.add_to_revision(self)
            reversion.set_comment(
                _("Undid marking action '%(action)s' as complete for report '%(report)s'") % {
                    'action': self, 'report': report})
            reversion.set_user(user)
        snapshots.delete()

    def get_status_summary(self):
        return ActionStatusSummaryIdentifier.for_action(self).get_data({'plan': self.plan})

    def get_timeliness(self):
        return ActionTimelinessIdentifier.for_action(self).get_data({'plan': self.plan})

    def get_color(self):
        if self.status and self.status.color:
            return self.status.color
        if self.implementation_phase and self.implementation_phase.color:
            return self.implementation_phase.color
        return None


@reversion.register()
class ActionResponsibleParty(OrderedModel):
    class Role(models.TextChoices):
        PRIMARY = 'primary', _('Primary responsible party')
        COLLABORATOR = 'collaborator', _('Collaborator')
        __empty__ = _('Unspecified')

    action = ParentalKey(
        Action, on_delete=models.CASCADE, related_name='responsible_parties',
        verbose_name=_('action')
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='responsible_actions', verbose_name=_('organization'),
        # FIXME: The following leads to a weird error in the action edit page, but only if Organization.i18n is there.
        # WTF? Commented out for now.
        # limit_choices_to=Q(dissolution_date=None),
    )
    role = models.CharField(max_length=40, choices=Role.choices, blank=True, null=True, verbose_name=_('role'))
    specifier = models.CharField(
        max_length=255,
        blank=True,
        verbose_name=_('specifier'),
        help_text=_('The responsibility domain for the organization'),
    )

    public_fields = [
        'id', 'action', 'organization', 'role', 'specifier', 'order',
    ]

    class Meta:
        ordering = ['action', 'order']
        index_together = (('action', 'order'),)
        unique_together = (('action', 'organization'),)
        verbose_name = _('action responsible party')
        verbose_name_plural = _('action responsible parties')

    def __str__(self):
        return str(self.organization)


class ActionContactPerson(OrderedModel):
    """A Person acting as a contact for an action"""
    class Role(models.TextChoices):
        EDITOR = 'editor', _('Editor')
        MODERATOR = 'moderator', _('Moderator')

    role = models.CharField(max_length=40, choices=Role.choices, default='moderator', blank=False, null=False, verbose_name=_('role'))

    action = ParentalKey(
        Action, on_delete=models.CASCADE, verbose_name=_('action'), related_name='contact_persons'
    )
    person = models.ForeignKey(
        'people.Person', on_delete=models.CASCADE, verbose_name=_('person')
    )
    primary_contact = models.BooleanField(
        default=False,
        verbose_name=_('primary contact person'),
        help_text=_('Is this person the primary contact person for the action?'),
    )

    public_fields = [
        'id', 'action', 'person', 'order', 'primary_contact',
    ]

    class Meta:
        ordering = ['action', 'order']
        index_together = (('action', 'order'),)
        unique_together = (('action', 'person',),)
        verbose_name = _('action contact person')
        verbose_name_plural = _('action contact persons')

    def __str__(self):
        return f'{str(self.person)}: {str(self.action)}'


class ActionSchedule(models.Model, PlanRelatedModel):
    """A schedule for an action with begin and end dates."""

    plan = ParentalKey('actions.Plan', on_delete=models.CASCADE, related_name='action_schedules')
    name = models.CharField(max_length=100)
    begins_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)

    i18n = TranslationField(fields=('name',), default_language_field='plan__primary_language')

    public_fields = [
        'id', 'plan', 'name', 'begins_at', 'ends_at'
    ]

    class Meta:
        ordering = ('plan', 'begins_at')
        verbose_name = _('action schedule')
        verbose_name_plural = _('action schedules')

    def __str__(self):
        return self.name


@reversion.register()
class ActionStatus(models.Model, PlanRelatedModel):
    """The current status for the action ("on time", "late", "completed", etc.)."""
    plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='action_statuses',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField(max_length=20)
    is_completed = models.BooleanField(default=False, verbose_name=_('is completed'))
    color = models.CharField(max_length=50, verbose_name=_('color'), blank=True, null=True)

    i18n = TranslationField(fields=('name',), default_language_field='plan__primary_language')

    public_fields = [
        'id', 'plan', 'name', 'identifier', 'is_completed'
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('action status')
        verbose_name_plural = _('action statuses')

    def __str__(self):
        return self.name


@reversion.register()
class ActionImplementationPhase(OrderedModel, PlanRelatedModel):
    plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='action_implementation_phases',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField(max_length=20)
    color = models.CharField(max_length=50, verbose_name=_('color'), blank=True, null=True)

    i18n = TranslationField(fields=('name',), default_language_field='plan__primary_language')

    public_fields = [
        'id', 'plan', 'order', 'name', 'identifier', 'color'
    ]

    class Meta:
        ordering = ('plan', 'order')
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('action implementation phase')
        verbose_name_plural = _('action implementation phases')

    def __str__(self):
        return self.name


class ActionDecisionLevel(models.Model, PlanRelatedModel):
    plan = models.ForeignKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='action_decision_levels',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=200, verbose_name=_('name'))
    identifier = IdentifierField()

    i18n = TranslationField(fields=('name',), default_language_field='plan__primary_language')

    public_fields = [
        'id', 'plan', 'name', 'identifier',
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)

    def __str__(self):
        return self.name


class ActionTaskQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))


class ActionTask(models.Model):
    """A task that should be completed during the execution of an action.

    The task will have at least a name and an estimate of the due date.
    """

    NOT_STARTED = 'not_started'
    IN_PROGRESS = 'in_progress'
    CANCELLED = 'cancelled'
    COMPLETED = 'completed'

    STATES = (
        (NOT_STARTED, _('not started')),
        (IN_PROGRESS, _('in progress')),
        (COMPLETED, _('completed')),
        (CANCELLED, _('cancelled')),
    )

    action = ParentalKey(
        Action, on_delete=models.CASCADE, related_name='tasks',
        verbose_name=_('action')
    )
    name = models.CharField(max_length=250, verbose_name=_('name'))
    state = models.CharField(max_length=20, choices=STATES, default=NOT_STARTED, verbose_name=_('state'))
    comment = RichTextField(null=True, blank=True, verbose_name=_('comment'))
    due_at = models.DateField(
        verbose_name=_('due date'),
        help_text=_('The date by which the task should be completed (deadline)')
    )
    completed_at = models.DateField(
        null=True, blank=True, verbose_name=_('completion date'),
        help_text=_('The date when the task was completed')
    )

    completed_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_('completed by'), editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False, verbose_name=_('created at'))
    modified_at = models.DateTimeField(auto_now=True, editable=False, verbose_name=_('modified at'))

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='action_task')

    i18n = TranslationField(fields=('name', 'comment'), default_language_field='action__plan__primary_language')

    objects = ActionTaskQuerySet.as_manager()

    verbose_name_partitive = pgettext_lazy('partitive', 'action task')

    public_fields = [
        'id', 'action', 'name', 'state', 'comment', 'due_at', 'completed_at', 'created_at', 'modified_at',
    ]

    class Meta:
        ordering = ('action', '-due_at')
        verbose_name = _('action task')
        verbose_name_plural = _('action tasks')
        constraints = [
            # Ensure a task is completed if and only if it has completed_at
            models.CheckConstraint(check=~Q(state='completed') | Q(completed_at__isnull=False),
                                   name='%(app_label)s_%(class)s_completed_at_if_completed'),
            models.CheckConstraint(check=Q(completed_at__isnull=True) | Q(state='completed'),
                                   name='%(app_label)s_%(class)s_completed_if_completed_at'),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        if self.state != ActionTask.COMPLETED and self.completed_at is not None:
            raise ValidationError({'completed_at': _('Non-completed tasks cannot have a completion date')})
        if self.state == ActionTask.COMPLETED and self.completed_at is None:
            raise ValidationError({'completed_at': _('Completed tasks must have a completion date')})
        # TODO: Put this check in, but the following won't work because self.action is None when creating a new
        # ActionTask as it is a ParentalKey.
        # today = self.action.plan.now_in_local_timezone().date()
        # if self.completed_at is not None and self.completed_at > today:
        #     raise ValidationError({'completed_at': _("Date can't be in the future")})

    @classmethod
    def from_serializable_data(cls, data, check_fks=True, strict_fks=True):
        if 'i18n' in data:
            del data['i18n']
        kwargs = {}
        to_delete = set()
        for field_name, value in data.items():
            field = None
            try:
                field = cls._meta.get_field(field_name)
            except FieldDoesNotExist:
                kwargs[field_name] = value
            if isinstance(field, TranslatedVirtualField):
                to_delete.add(field_name)
        for f in to_delete:
            del data[f]
        del data['action']
        return model_from_serializable_data(cls, data, check_fks=check_fks, strict_fks=strict_fks)

    def get_notification_context(self, plan=None):
        if plan is None:
            plan = self.action.plan
        return {
            'action': self.action.get_notification_context(plan),
            'name': self.name,
            'due_at': self.due_at,
            'state': self.state
        }


class ActionImpact(OrderedModel, PlanRelatedModel):
    """An impact classification for an action in an action plan."""

    plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='action_impacts',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=200, verbose_name=_('name'))
    identifier = IdentifierField()

    i18n = TranslationField(fields=('name',), default_language_field='plan__primary_language')

    public_fields = [
        'id', 'plan', 'name', 'identifier', 'order',
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'order')
        verbose_name = _('action impact class')
        verbose_name_plural = _('action impact classes')

    def __str__(self):
        return '%s (%s)' % (self.name, self.identifier)


class ActionLink(OrderedModel):
    """A link related to an action."""

    action = ParentalKey(Action, on_delete=models.CASCADE, verbose_name=_('action'), related_name='links')
    url = models.URLField(max_length=400, verbose_name=_('URL'), validators=[URLValidator(('http', 'https'))])
    title = models.CharField(max_length=254, verbose_name=_('title'), blank=True)

    public_fields = [
        'id', 'action', 'url', 'title', 'order'
    ]

    class Meta:
        ordering = ['action', 'order']
        index_together = (('action', 'order'),)
        verbose_name = _('action link')
        verbose_name_plural = _('action links')

    def __str__(self):
        if self.title:
            return f'{self.title}: {self.url}'
        return self.url


class ActionStatusUpdate(models.Model):
    action = models.ForeignKey(
        Action, on_delete=models.CASCADE, related_name='status_updates',
        verbose_name=_('action')
    )
    title = models.CharField(max_length=200, verbose_name=_('title'))
    date = models.DateField(verbose_name=_('date'), blank=True)
    author = models.ForeignKey(
        'people.Person', on_delete=models.SET_NULL, related_name='status_updates',
        null=True, blank=True, verbose_name=_('author')
    )
    content = models.TextField(verbose_name=_('content'))

    created_at = models.DateField(verbose_name=_('created at'), editable=False, blank=True)
    modified_at = models.DateField(verbose_name=_('created at'), editable=False, blank=True)
    created_by = models.ForeignKey(
        User, null=True, blank=True, on_delete=models.SET_NULL,
        verbose_name=_('created by'), editable=False,
    )

    public_fields = [
        'id', 'action', 'title', 'date', 'author', 'content', 'created_at', 'modified_at',
    ]

    class Meta:
        verbose_name = _('action status update')
        verbose_name_plural = _('action status updates')
        ordering = ('-date',)

    def save(self, *args, **kwargs):
        now = self.action.plan.now_in_local_timezone()
        if self.pk is None:
            if self.date is None:
                self.date = now.date()
            if self.created_at is None:
                self.created_at = now.date()
        if self.modified_at is None:
            self.modified_at = now.date()
        return super().save(*args, **kwargs)

    def __str__(self):
        return '%s – %s – %s' % (self.action, self.created_at, self.title)


class ImpactGroupAction(models.Model):
    group = models.ForeignKey(
        'actions.ImpactGroup', verbose_name=_('name'), on_delete=models.CASCADE,
        related_name='actions',
    )
    action = models.ForeignKey(
        Action, verbose_name=_('action'), on_delete=models.CASCADE,
        related_name='impact_groups',
    )
    impact = models.ForeignKey(
        ActionImpact, verbose_name=_('impact'), on_delete=models.PROTECT,
        related_name='+',
    )

    public_fields = [
        'id', 'group', 'action', 'impact',
    ]

    class Meta:
        unique_together = (('group', 'action'),)
        verbose_name = _('impact group action')
        verbose_name_plural = _('impact group actions')

    def __str__(self):
        return "%s ➜ %s" % (self.action, self.group)


class ActionModeratorApprovalTask(Task):
    def locked_for_user(self, obj: Action, user: User):
        return not user.can_publish_action(obj)

    def get_actions(self, obj: Action, user: User):
        if user.can_publish_action(obj):
            return [
                ("approve", _("Approve"), False),
                # ("approve", _("Approve with comment"), True),
                ("reject", _("Request changes"), True),
            ]
        else:
            return []
