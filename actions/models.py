import re
import logging
from datetime import date

from django.db import models
from django.db.models import Q
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from parler.models import TranslatableModel, TranslatedFields
from django_orghierarchy.models import Organization

from aplans.utils import IdentifierField, OrderedModel
from aplans.model_images import ModelWithImage

from .monitoring_quality import determine_monitoring_quality


logger = logging.getLogger(__name__)
User = get_user_model()


class Plan(ModelWithImage, models.Model):
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = IdentifierField(unique=True)
    root_org = models.ForeignKey(
        'django_orghierarchy.Organization', blank=True, null=True, on_delete=models.PROTECT,
        verbose_name=_('root organization')
    )

    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    site_url = models.URLField(blank=True, null=True, verbose_name=_('site URL'))
    actions_locked = models.BooleanField(
        default=False, verbose_name=_('actions locked'),
        help_text=_('Can actions be added and the official metadata edited?'),
    )
    allow_images_for_actions = models.BooleanField(
        default=True, verbose_name=_('allow images for actions'),
        help_text=_('Should custom images for individual actions be allowed')
    )

    general_admins = models.ManyToManyField(
        User, blank=True, related_name='general_admin_plans',
        verbose_name=_('general administrators'),
        help_text=_('Users that can modify everything related to the action plan')
    )

    public_fields = [
        'id', 'name', 'identifier', 'root_org', 'image_url', 'action_schedules',
        'actions', 'category_types', 'action_statuses', 'indicator_levels',
        'action_impacts', 'blog_posts', 'static_pages', 'general_content',
        'impact_groups', 'monitoring_quality_points',
    ]

    class Meta:
        verbose_name = _('plan')
        verbose_name_plural = _('plans')
        get_latest_by = 'created_at'
        ordering = ('created_at',)

    def __str__(self):
        return self.name

    def get_last_action_identifier(self):
        return self.actions.order_by('order').values_list('identifier', flat=True).last()


def latest_plan():
    if Plan.objects.exists():
        return Plan.objects.latest().id
    else:
        return None


class ActionQuerySet(models.QuerySet):
    def modifiable_by(self, user):
        if user.is_superuser:
            return self
        query = Q(plan__in=user.general_admin_plans.all())
        person = user.get_corresponding_person()
        if person is not None:
            query |= Q(contact_persons__person=person)
        query |= Q(responsible_parties__organization__in=user.get_adminable_organizations())
        return self.filter(query).distinct()

    def unmerged(self):
        return self.filter(merged_with__isnull=True)

    def active(self):
        return self.umerged().filter(status__is_completed=False)


class Action(ModelWithImage, OrderedModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, default=latest_plan, related_name='actions',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=1000, verbose_name=_('name'))
    official_name = models.CharField(
        null=True, blank=True, max_length=1000,
        verbose_name=_('official name'),
        help_text=_('The name as approved by an official party')
    )
    identifier = IdentifierField(
        help_text=_('The identifier for this action (e.g. number)')
    )
    description = models.TextField(
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
    internal_priority_comment = models.TextField(
        blank=True, null=True, verbose_name=_('internal priority comment')
    )
    status = models.ForeignKey(
        'ActionStatus', blank=True, null=True, on_delete=models.SET_NULL,
        verbose_name=_('status'),
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

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='action')

    objects = ActionQuerySet.as_manager()

    # Used by GraphQL + REST API code
    public_fields = [
        'id', 'plan', 'name', 'official_name', 'identifier', 'description', 'status',
        'completion', 'schedule', 'decision_level', 'responsible_parties',
        'categories', 'indicators', 'contact_persons', 'updated_at', 'tasks',
        'related_indicators', 'impact', 'status_updates', 'merged_with', 'merged_actions',
        'impact_groups', 'monitoring_quality_points',
    ]

    class Meta:
        verbose_name = _('action')
        verbose_name_plural = _('actions')
        ordering = ('plan', 'order')
        index_together = (('plan', 'order'),)
        permissions = (
            ('admin_action', _("Can administrate all actions")),
        )

    def __str__(self):
        return "%s. %s" % (self.identifier, self.name)

    def clean(self):
        if self.merged_with is not None:
            other = self.merged_with
            if other.merged_with == self:
                raise ValidationError({'merged_with': _('Other action is merged with this one')})
        # FIXME: Make sure FKs and M2Ms point to objects that are within the
        # same action plan.

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
            logger.error('Unknown action status IDs: %s' % set(by_id.keys()))
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

    def recalculate_status(self):
        if self.merged_with is not None:
            return

        if self.status is not None and self.status.is_completed:
            if self.completion != 100:
                self.completion = 100
                self.save(update_fields=['completion'])
            return

        determine_monitoring_quality(self, self.plan.monitoring_quality_points.all())

        tasks = self.tasks.exclude(state=ActionTask.CANCELLED).only('due_at', 'completed_at')
        update_fields = []

        indicator_status = self._calculate_status_from_indicators()
        if indicator_status:
            new_completion = indicator_status['completion']
        else:
            new_completion = None

        if self.completion != new_completion:
            update_fields.append('completion')
            self.completion = new_completion
            self.updated_at = timezone.now()
            update_fields.append('updated_at')

        status = self._determine_status(tasks, indicator_status)
        if status is not None and status.id != self.status_id:
            self.status = status
            update_fields.append('status')

        if not update_fields:
            return
        self.save(update_fields=update_fields)

    def set_categories(self, type, categories):
        if isinstance(type, str):
            type = self.plan.category_types.get(identifier=type)
        all_cats = {x.identifier: x for x in type.categories.all()}

        existing_cats = set(self.categories.filter(type=type))
        new_cats = set()
        for cat in categories:
            if isinstance(cat, str):
                cat = all_cats[cat]
            new_cats.add(cat)

        for cat in existing_cats - new_cats:
            self.categories.remove(cat)
        for cat in new_cats - existing_cats:
            self.categories.add(cat)

    def get_notification_context(self):
        change_url = reverse('admin:actions_action_change', args=(self.id,))
        return {
            'id': self.id, 'identifier': self.identifier, 'name': self.name, 'change_url': change_url,
            'updated_at': self.updated_at
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


class ActionResponsibleParty(OrderedModel):
    action = models.ForeignKey(
        Action, on_delete=models.CASCADE, related_name='responsible_parties',
        verbose_name=_('action')
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='responsible_actions',
        limit_choices_to=Q(dissolution_date=None), verbose_name=_('organization'),
    )

    class Meta:
        ordering = ['action', 'order']
        index_together = (('action', 'order'),)
        unique_together = (('action', 'organization'),)
        verbose_name = _('action responsible party')
        verbose_name_plural = _('action responsible parties')

    def __str__(self):
        return str(self.organization)


class ActionContactPerson(OrderedModel):
    action = models.ForeignKey(
        Action, on_delete=models.CASCADE, verbose_name=_('action'), related_name='contact_persons'
    )
    person = models.ForeignKey(
        'people.Person', on_delete=models.CASCADE, verbose_name=_('person')
    )

    class Meta:
        ordering = ['action', 'order']
        index_together = (('action', 'order'),)
        unique_together = (('action', 'person',),)
        verbose_name = _('action contact person')
        verbose_name_plural = _('action contact persons')

    def __str__(self):
        return str(self.person)


class ActionSchedule(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='action_schedules')
    name = models.CharField(max_length=100)
    begins_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)

    class Meta(OrderedModel.Meta):
        ordering = ('plan', 'begins_at')
        verbose_name = _('action schedule')
        verbose_name_plural = _('action schedules')

    def __str__(self):
        return self.name


class ActionStatus(models.Model):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='action_statuses',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField(max_length=20)
    is_completed = models.BooleanField(default=False, verbose_name=_('is completed'))

    class Meta:
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('action status')
        verbose_name_plural = _('action statuses')

    def __str__(self):
        return self.name


class ActionDecisionLevel(models.Model):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='action_decision_levels',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=200, verbose_name=_('name'))
    identifier = IdentifierField()

    class Meta:
        unique_together = (('plan', 'identifier'),)

    def __str__(self):
        return self.name


class ActionTaskQuerySet(models.QuerySet):
    def active(self):
        return self.exclude(state__in=(ActionTask.CANCELLED, ActionTask.COMPLETED))


class ActionTask(models.Model):
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

    action = models.ForeignKey(
        Action, on_delete=models.CASCADE, related_name='tasks',
        verbose_name=_('action')
    )
    name = models.CharField(max_length=250, verbose_name=_('name'))
    state = models.CharField(max_length=20, choices=STATES, default=NOT_STARTED, verbose_name=_('state'))
    comment = models.TextField(null=True, blank=True, verbose_name=_('comment'))
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

    objects = ActionTaskQuerySet.as_manager()

    class Meta:
        ordering = ('action', 'due_at')
        verbose_name = _('action task')
        verbose_name_plural = _('action tasks')

    def __str__(self):
        return self.name

    def clean(self):
        if self.state == ActionTask.COMPLETED and self.completed_at is None:
            raise ValidationError({'completed_at': _('Completed tasks must have a completion date')})
        if self.completed_at is not None and self.completed_at > date.today():
            raise ValidationError({'completed_at': _("Date can't be in the future")})

    def get_notification_context(self):
        return {
            'action': self.action.get_notification_context(),
            'name': self.name,
            'due_at': self.due_at,
            'state': self.state
        }


class ActionImpact(OrderedModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='action_impacts',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=200, verbose_name=_('name'))
    identifier = IdentifierField()

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'order')
        verbose_name = _('action impact class')
        verbose_name_plural = _('action impact classes')

    def __str__(self):
        return '%s (%s)' % (self.name, self.identifier)


class CategoryType(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='category_types')
    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField()
    editable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('editable for actions'),
    )
    editable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('editable for indicators'),
    )

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'name')
        verbose_name = _('category type')
        verbose_name_plural = _('category types')

    def __str__(self):
        return "%s (%s:%s)" % (self.name, self.plan.identifier, self.identifier)


class Category(OrderedModel, ModelWithImage):
    type = models.ForeignKey(
        CategoryType, on_delete=models.PROTECT, related_name='categories',
        verbose_name=_('type')
    )
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
        verbose_name=_('parent category')
    )
    short_description = models.CharField(
        max_length=200, blank=True, verbose_name=_('short description')
    )

    class Meta:
        unique_together = (('type', 'identifier'),)
        verbose_name = _('category')
        verbose_name_plural = _('categories')
        ordering = ('type', 'identifier')

    def clean(self):
        if self.parent_id is not None:
            seen_categories = {self.id}
            obj = self.parent
            while obj is not None:
                if obj.id in seen_categories:
                    raise ValidationError({'parent': _('Parent forms a loop. Leave empty if top-level category.')})
                seen_categories.add(obj.id)
                obj = obj.parent

    def __str__(self):
        if self.identifier and self.identifier[0].isnumeric():
            return "%s %s" % (self.identifier, self.name)
        else:
            return self.name


class Scenario(models.Model):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='scenarios',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = IdentifierField()
    description = models.TextField(null=True, blank=True, verbose_name=_('description'))

    class Meta:
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('scenario')
        verbose_name_plural = _('scenarios')

    def __str__(self):
        return self.name


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

    class Meta:
        verbose_name = _('action status update')
        verbose_name_plural = _('action status updates')
        ordering = ('-date',)

    def __str__(self):
        return '%s – %s – %s' % (self.action, self.created_at, self.title)


def validate_hex_color(s):
    match = re.search(r'^#(?:[0-9a-fA-F]{3}){1,2}$', s)
    if not match:
        raise ValidationError(
            _('%(color)s is not a hex color (#112233)'),
            params={'color': s},
        )


class ImpactGroup(TranslatableModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='impact_groups',
        verbose_name=_('plan')
    )
    identifier = IdentifierField()
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, related_name='children', null=True, blank=True,
        verbose_name=_('parent')
    )
    weight = models.FloatField(verbose_name=_('weight'), null=True, blank=True)
    color = models.CharField(
        max_length=16, verbose_name=_('color'), null=True, blank=True,
        validators=[validate_hex_color]
    )

    translations = TranslatedFields(
        name=models.CharField(
            verbose_name=_('name'), max_length=200
        ),
    )

    public_fields = [
        'id', 'plan', 'identifier', 'parent', 'weight', 'name', 'color', 'actions',
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('scenario')
        verbose_name_plural = _('scenarios')
        ordering = ('plan', '-weight')

    def __str__(self):
        return self.name


class ImpactGroupAction(models.Model):
    group = models.ForeignKey(
        ImpactGroup, verbose_name=_('name'), on_delete=models.CASCADE,
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

    class Meta:
        unique_together = (('group', 'action'),)
        verbose_name = _('impact group action')
        verbose_name_plural = _('impact group actions')

    def __str__(self):
        return "%s ➜ %s" % (self.action, self.group)


class MonitoringQualityPoint(OrderedModel, TranslatableModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='monitoring_quality_points',
        verbose_name=_('plan')
    )
    identifier = IdentifierField()
    translations = TranslatedFields(
        name=models.CharField(
            max_length=100, verbose_name=_('name'),
        ),
        description_yes=models.CharField(
            max_length=200, verbose_name=_("description when action fulfills criteria")
        ),
        description_no=models.CharField(
            max_length=200, verbose_name=_("description when action doesn\'t fulfill criteria")
        ),
    )

    class Meta:
        verbose_name = _('monitoring quality point')
        verbose_name_plural = _('monitoring quality points')
        unique_together = (('plan', 'order'),)
        ordering = ('plan', 'order')

    def __str__(self):
        return self.name
