from __future__ import annotations
import typing
import logging
from datetime import date

from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models import Max, Q
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.core.fields import RichTextField
from wagtail.search import index
from wagtail.search.queryset import SearchableQuerySetMixin

import reversion

from aplans.utils import (
    IdentifierField, OrderedModel, PlanRelatedModel, generate_identifier
)
from orgs.models import Organization
from users.models import User

from .attributes import AttributeType, AttributeTypeChoiceOption
from ..monitoring_quality import determine_monitoring_quality

if typing.TYPE_CHECKING:
    from .plan import Plan


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

    def unmerged(self):
        return self.filter(merged_with__isnull=True)

    def active(self):
        return self.unmerged().exclude(status__is_completed=True)


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


@reversion.register()
class Action(OrderedModel, ClusterableModel, PlanRelatedModel, index.Indexed):
    """One action/measure tracked in an action plan."""

    plan: Plan = ParentalKey(
        'actions.Plan', on_delete=models.CASCADE, related_name='actions',
        verbose_name=_('plan')
    )
    primary_org = models.ForeignKey(
        'orgs.Organization', verbose_name=_('primary organization'),
        null=True, on_delete=models.SET_NULL,
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
        'Category', blank=True, verbose_name=_('categories')
    )
    indicators = models.ManyToManyField(
        'indicators.Indicator', blank=True, verbose_name=_('indicators'),
        through='indicators.ActionIndicator', related_name='actions'
    )

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

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='action')

    i18n = TranslationField(fields=('name', 'official_name', 'description', 'manual_status_reason'))

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
    ]
    search_auto_update = True

    # Used by GraphQL + REST API code
    public_fields = [
        'id', 'plan', 'name', 'official_name', 'identifier', 'lead_paragraph', 'description', 'status',
        'completion', 'schedule', 'schedule_continuous', 'decision_level', 'responsible_parties',
        'categories', 'indicators', 'contact_persons', 'updated_at', 'start_date', 'end_date', 'tasks',
        'related_indicators', 'impact', 'status_updates', 'merged_with', 'merged_actions',
        'impact_groups', 'monitoring_quality_points', 'implementation_phase',
        'manual_status_reason', 'links', 'primary_org', 'order'
    ]

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

    def get_next_action(self):
        return Action.objects.filter(plan=self.plan_id, order__gt=self.order).unmerged().first()

    def get_previous_action(self):
        return Action.objects.filter(plan=self.plan_id, order__lt=self.order).unmerged().order_by('-order').first()

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
                last_goal = ind.goals.filter(plan=self.plan).latest()
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
            closest_goal = ind.goals.filter(plan=self.plan, date__lte=latest_value.date).last()
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
        return dict(completion=completion, is_late=is_late)

    def _calculate_completion_from_tasks(self, tasks):
        if not tasks:
            return None
        n_completed = len(list(filter(lambda x: x.completed_at is not None, tasks)))
        return dict(completion=int(n_completed * 100 / len(tasks)))

    def _determine_status(self, tasks, indicator_status):
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

        today = date.today()

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

    def handle_admin_save(self):
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

    def generate_identifier(self):
        self.identifier = generate_identifier(self.plan.actions.all(), 'a', 'identifier')

    def get_notification_context(self, plan=None):
        if plan is None:
            plan = self.plan
        if plan.uses_wagtail:
            change_url = reverse('actions_action_modeladmin_edit', kwargs=dict(instance_pk=self.id))
        else:
            change_url = reverse('admin:actions_action_change', args=(self.id,))
        return {
            'id': self.id, 'identifier': self.identifier, 'name': self.name, 'change_url': change_url,
            'updated_at': self.updated_at, 'view_url': self.get_view_url(plan), 'order': self.order,
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

    def get_view_url(self, plan=None):
        if plan is None:
            plan = self.plan
        if not plan.site_url:
            return None
        if plan.site_url.startswith('http'):
            return '{}/actions/{}'.format(plan.site_url, self.identifier)
        else:
            return 'https://{}/actions/{}'.format(plan.site_url, self.identifier)

    def get_primary_language(self):
        return self.plan.primary_language


class ActionResponsibleParty(OrderedModel):
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

    public_fields = [
        'id', 'action', 'organization', 'order',
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
        return str(self.person)


class ActionSchedule(models.Model, PlanRelatedModel):
    """A schedule for an action with begin and end dates."""

    plan = ParentalKey('actions.Plan', on_delete=models.CASCADE, related_name='action_schedules')
    name = models.CharField(max_length=100)
    begins_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)

    i18n = TranslationField(fields=('name',))

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

    i18n = TranslationField(fields=('name',))

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

    i18n = TranslationField(fields=('name',))

    public_fields = [
        'id', 'plan', 'order', 'name', 'identifier',
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

    i18n = TranslationField(fields=('name',))

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

    i18n = TranslationField(fields=('name', 'comment'))

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
        if self.completed_at is not None and self.completed_at > date.today():
            raise ValidationError({'completed_at': _("Date can't be in the future")})

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

    i18n = TranslationField(fields=('name',))

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
    date = models.DateField(verbose_name=_('date'), default=date.today)
    author = models.ForeignKey(
        'people.Person', on_delete=models.SET_NULL, related_name='status_updates',
        null=True, blank=True, verbose_name=_('author')
    )
    content = models.TextField(verbose_name=_('content'))

    created_at = models.DateField(
        verbose_name=_('created at'), editable=False, auto_now_add=True
    )
    modified_at = models.DateField(
        verbose_name=_('created at'), editable=False, auto_now=True
    )
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


@reversion.register()
class ActionAttributeType(AttributeType, PlanRelatedModel):
    """Type of attributes that can be given to actions in a specific plan."""
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='action_attribute_types')

    class Meta(AttributeType.Meta):
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('action attribute type')
        verbose_name_plural = _('action attribute types')

    def set_action_value(self, action, vals):
        # TODO: Partly duplicated in category.py
        assert action.plan == self.plan

        if self.format == self.AttributeFormat.ORDERED_CHOICE:
            val = vals.get('choice')
            existing = self.choice_attributes.filter(action=action)
            if existing:
                existing.delete()
            if val is not None:
                self.choice_attributes.create(action=action, choice=val)
        elif self.format == self.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT:
            choice_val = vals.get('choice')
            text_val = vals.get('text')
            existing = self.choice_with_text_attributes.filter(action=action)
            if existing:
                existing.delete()
            if choice_val is not None or text_val:
                self.choice_with_text_attributes.create(action=action, choice=choice_val, text=text_val)
        elif self.format == self.AttributeFormat.RICH_TEXT:
            val = vals.get('text')
            try:
                obj = self.richtext_attributes.get(action=action)
            except self.richtext_attributes.model.DoesNotExist:
                if val:
                    obj = self.richtext_attributes.create(action=action, text=val)
            else:
                if not val:
                    obj.delete()
                else:
                    obj.text = val
                    obj.save()
        elif self.format == self.AttributeFormat.NUMERIC:
            val = vals.get('value')
            try:
                obj = self.numeric_value_attributes.get(action=action)
            except self.numeric_value_attributes.model.DoesNotExist:
                if val is not None:
                    obj = self.numeric_value_attributes.create(action=action, value=val)
            else:
                if val is None:
                    obj.delete()
                else:
                    obj.value = val
                    obj.save()
        else:
            raise Exception(f"Unsupported attribute type format: {self.format}")


class ActionAttributeTypeChoiceOption(AttributeTypeChoiceOption):
    type = ParentalKey(ActionAttributeType, on_delete=models.CASCADE, related_name='choice_options')

    class Meta(AttributeTypeChoiceOption.Meta):
        verbose_name = _('action attribute type choice option')
        verbose_name_plural = _('action attribute type choice options')


class ActionAttributeRichText(models.Model):
    """Rich text value for an action attribute."""
    type = models.ForeignKey(ActionAttributeType, on_delete=models.CASCADE, related_name='richtext_attributes')
    action = ParentalKey(Action, on_delete=models.CASCADE, related_name='richtext_attributes')
    text = RichTextField(verbose_name=_('Text'))

    public_fields = [
        'id', 'type', 'action', 'text',
    ]

    class Meta:
        unique_together = ('action', 'type')

    def __str__(self):
        return '%s for %s' % (self.type, self.action)


class ActionAttributeNumericValue(models.Model):
    type = models.ForeignKey(ActionAttributeType, on_delete=models.CASCADE, related_name='numeric_value_attributes')
    action = ParentalKey(Action, on_delete=models.CASCADE, related_name='numeric_value_attributes')
    value = models.FloatField()

    public_fields = [
        'id', 'type', 'action', 'value',
    ]

    class Meta:
        unique_together = ('action', 'type')

    def __str__(self):
        return '%s (%s) for %s' % (self.value, self.type, self.action)


class ActionAttributeChoice(models.Model):
    type = models.ForeignKey(ActionAttributeType, on_delete=models.CASCADE, related_name='choice_attributes')
    action = ParentalKey(Action, on_delete=models.CASCADE, related_name='choice_attributes')
    choice = models.ForeignKey(
        ActionAttributeTypeChoiceOption, on_delete=models.CASCADE, related_name='choice_attributes'
    )

    class Meta:
        unique_together = ('action', 'type')

    def __str__(self):
        return '%s (%s) for %s' % (self.choice, self.type, self.action)


class ActionAttributeChoiceWithText(models.Model):
    type = models.ForeignKey(ActionAttributeType, on_delete=models.CASCADE, related_name='choice_with_text_attributes')
    action = ParentalKey(Action, on_delete=models.CASCADE, related_name='choice_with_text_attributes')
    choice = models.ForeignKey(
        ActionAttributeTypeChoiceOption, blank=True, null=True, on_delete=models.CASCADE,
        related_name='choice_with_text_attributes',
    )
    text = RichTextField(verbose_name=_('Text'), blank=True, null=True)

    class Meta:
        unique_together = ('action', 'type')

    def __str__(self):
        return '%s; %s (%s) for %s' % (self.choice, self.text, self.type, self.action)
