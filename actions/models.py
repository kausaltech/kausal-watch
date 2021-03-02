import logging
import re
from datetime import date

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models
from django.db.models import Q, Max
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.utils.translation import pgettext_lazy
import reversion
from tinycss2.color3 import parse_color
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.core.fields import RichTextField
from wagtail.core.models import Collection, Site

from django_orghierarchy.models import Organization
from aplans.utils import ChoiceArrayField, IdentifierField, OrderedModel, PlanRelatedModel

from .monitoring_quality import determine_monitoring_quality

logger = logging.getLogger(__name__)
User = get_user_model()


def get_supported_languages():
    for x in settings.LANGUAGES:
        yield x


def get_default_language():
    return settings.LANGUAGES[0][0]


def validate_css_color(s):
    if parse_color(s) is None:
        raise ValidationError(
            _('%(color)s is not a CSS color (e.g., "#112233", "red" or "rgb(0, 255, 127)")'),
            params={'color': s},
        )


class PlanQuerySet(models.QuerySet):
    def for_hostname(self, hostname):
        hostname = hostname.lower()

        # Support localhost-based URLs for development
        parts = hostname.split('.')
        if len(parts) == 2 and parts[1] == 'localhost':
            return self.filter(identifier=parts[0])

        return self.filter(domains__hostname=hostname.lower())


class Plan(ClusterableModel):
    """The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = IdentifierField(unique=True)
    image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    created_at = models.DateTimeField(auto_now_add=True, editable=False)
    site_url = models.URLField(
        blank=True, null=True, verbose_name=_('site URL'),
        validators=[URLValidator(('http', 'https'))]
    )
    actions_locked = models.BooleanField(
        default=False, verbose_name=_('actions locked'),
        help_text=_('Can actions be added and the official metadata edited?'),
    )
    allow_images_for_actions = models.BooleanField(
        default=True, verbose_name=_('allow images for actions'),
        help_text=_('Should custom images for individual actions be allowed')
    )
    organization = models.ForeignKey(
        'django_orghierarchy.Organization', related_name='plans', on_delete=models.PROTECT,
        verbose_name=_('main organization for the plan'),
    )

    general_admins = models.ManyToManyField(
        User, blank=True, related_name='general_admin_plans',
        verbose_name=_('general administrators'),
        help_text=_('Users that can modify everything related to the action plan')
    )

    site = models.OneToOneField(
        Site, null=True, on_delete=models.SET_NULL, editable=False, related_name='plan',
    )
    root_collection = models.OneToOneField(
        Collection, null=True, on_delete=models.PROTECT, editable=False, related_name='plan',
    )
    admin_group = models.OneToOneField(
        Group, null=True, on_delete=models.PROTECT, editable=False, related_name='admin_for_plan',
    )
    contact_person_group = models.OneToOneField(
        Group, null=True, on_delete=models.PROTECT, editable=False, related_name='contact_person_for_plan',
    )

    primary_language = models.CharField(max_length=8, choices=get_supported_languages(), default=get_default_language)
    other_languages = ChoiceArrayField(
        models.CharField(max_length=8, choices=get_supported_languages(), default=get_default_language),
        default=list, null=True, blank=True
    )
    accessibility_statement_url = models.URLField(
        blank=True,
        null=True,
        verbose_name=_('URL to accessibility statement'),
    )
    uses_wagtail = models.BooleanField(default=True)
    statuses_updated_manually = models.BooleanField(default=False)

    related_organizations = models.ManyToManyField(
        'django_orghierarchy.Organization', blank=True, related_name='related_plans'
    )

    cache_invalidated_at = models.DateTimeField(auto_now=True)
    i18n = TranslationField(fields=['name'])

    public_fields = [
        'id', 'name', 'identifier', 'image', 'action_schedules',
        'actions', 'category_types', 'action_statuses', 'indicator_levels',
        'action_impacts', 'general_content', 'impact_groups',
        'monitoring_quality_points', 'scenarios',
        'primary_language', 'other_languages', 'accessibility_statement_url',
        'action_implementation_phases',
    ]

    objects = models.Manager.from_queryset(PlanQuerySet)()

    class Meta:
        verbose_name = _('plan')
        verbose_name_plural = _('plans')
        get_latest_by = 'created_at'
        ordering = ('created_at',)

    def __str__(self):
        return self.name

    def get_last_action_identifier(self):
        return self.actions.order_by('order').values_list('identifier', flat=True).last()

    def clean(self):
        if self.primary_language in self.other_languages:
            raise ValidationError({'other_languages': _('Primary language must not be selected')})

    def get_related_organizations(self):
        all_related = self.related_organizations.all() | self.related_organizations.all().get_descendants()
        if self.organization:
            all_related |= Organization.objects.filter(id=self.id) | self.organization.get_descendants(True)
        return all_related

    @property
    def root_page(self):
        if self.site_id is None:
            return None
        return self.site.root_page

    def save(self, *args, **kwargs):
        ret = super().save(*args, **kwargs)

        update_fields = []
        if self.root_collection is None:
            obj = Collection.get_first_root_node().add_child(name=self.name)
            self.root_collection = obj
            update_fields.append('root_collection')
        else:
            if self.root_collection.name != self.name:
                self.root_collection.name = self.name
                self.root_collection.save(update_fields=['name'])

        if self.site is None:
            from pages.models import PlanRootPage
            from wagtail.core.models import Page

            root_page = Page.get_first_root_node().add_child(
                instance=PlanRootPage(title=self.name, slug=self.identifier, url_path='')
            )
            site = Site(site_name=self.name, hostname=self.site_url, root_page=root_page)
            site.save()
            self.site = site
            update_fields.append('site')
        else:
            # FIXME: Update Site and PlanRootPage attributes
            pass

        group_name = '%s admins' % self.name
        if self.admin_group is None:
            obj = Group.objects.create(name='%s admins' % group_name)
            self.admin_group = obj
            update_fields.append('admin_group')
        else:
            if self.admin_group.name != group_name:
                self.admin_group.name = group_name
                self.admin_group.save()

        group_name = '%s contact persons' % self.name
        if self.contact_person_group is None:
            obj = Group.objects.create(name=group_name)
            self.contact_person_group = obj
            update_fields.append('contact_person_group')
        else:
            if self.contact_person_group.name != group_name:
                self.contact_person_group.name = group_name
                self.contact_person_group.save()

        if update_fields:
            super().save(update_fields=update_fields)
        return ret

    def get_site_notification_context(self):
        return dict(
            view_url=self.site_url,
            title=self.general_content.site_title
        )

    def invalidate_cache(self):
        logger.info('Invalidate cache for %s' % self)
        self.cache_invalidated_at = timezone.now()
        super().save(update_fields=['cache_invalidated_at'])


class PlanDomain(models.Model):
    """A domain (hostname) where an UI for a Plan might live."""

    plan = ParentalKey(
        Plan, on_delete=models.CASCADE, related_name='domains', verbose_name=_('plan')
    )
    hostname = models.CharField(max_length=200, verbose_name=_('host name'), unique=True, db_index=True)
    google_site_verification_tag = models.CharField(max_length=50, null=True, blank=True)
    matomo_analytics_url = models.CharField(max_length=100, null=True, blank=True)

    def validate_hostname(self):
        dn = self.hostname
        if not isinstance(dn, str):
            return False
        if not dn.islower():
            return False
        if dn.endswith('.'):
            dn = dn[:-1]
        if len(dn) < 1 or len(dn) > 253:
            return False
        ldh_re = re.compile('^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$',
                            re.IGNORECASE)
        return all(ldh_re.match(x) for x in dn.split('.'))

    def clean(self):
        if not self.validate_hostname():
            raise ValidationError({'hostname': _('Hostname must be a fully qualified domain name in lower-case only')})

    def __str__(self):
        return str(self.hostname)

    class Meta:
        verbose_name = _('plan domain')
        verbose_name_plural = _('plan domains')


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
        return self.unmerged().exclude(status__is_completed=True)


class Action(OrderedModel, ClusterableModel, PlanRelatedModel):
    """One action/measure tracked in an action plan."""

    plan = ParentalKey(
        Plan, on_delete=models.CASCADE, related_name='actions',
        verbose_name=_('plan')
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
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
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

    i18n = TranslationField(fields=('name', 'official_name', 'description'))

    objects = ActionQuerySet.as_manager()

    # Used by GraphQL + REST API code
    public_fields = [
        'id', 'plan', 'name', 'official_name', 'identifier', 'description', 'status',
        'completion', 'schedule', 'decision_level', 'responsible_parties',
        'categories', 'indicators', 'contact_persons', 'updated_at', 'tasks',
        'related_indicators', 'impact', 'status_updates', 'merged_with', 'merged_actions',
        'impact_groups', 'monitoring_quality_points', 'implementation_phase',
        'manual_status_reason',
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
        return "%s. %s" % (self.identifier, self.name)

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
            logger.warning('Unable to determine action statuses for plan %s: right statuses missing' % self.plan.identifier)
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
        if self.merged_with is not None or self.manual_status or self.plan.statuses_updated_manually:
            return

        if self.status is not None and self.status.is_completed:
            if self.status.identifier == 'completed' and self.completion != 100:
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

        if self.completion != new_completion or force_update:
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

    def handle_admin_save(self):
        self.recalculate_status(force_update=True)

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
        plan = self.plan
        if plan.uses_wagtail:
            change_url = reverse('actions_action_modeladmin_edit', kwargs=dict(instance_pk=self.id))
        else:
            change_url = reverse('admin:actions_action_change', args=(self.id,))
        return {
            'id': self.id, 'identifier': self.identifier, 'name': self.name, 'change_url': change_url,
            'updated_at': self.updated_at, 'view_url': self.get_view_url(), 'order': self.order,
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

    def get_view_url(self):
        plan = self.plan
        if not plan or not plan.site_url:
            return None
        if plan.site_url.startswith('http'):
            return '{}/actions/{}'.format(plan.site_url, self.identifier)
        else:
            return 'https://{}/actions/{}'.format(plan.site_url, self.identifier)


class ActionResponsibleParty(OrderedModel):
    action = ParentalKey(
        Action, on_delete=models.CASCADE, related_name='responsible_parties',
        verbose_name=_('action')
    )
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='responsible_actions',
        limit_choices_to=Q(dissolution_date=None), verbose_name=_('organization'),
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

    plan = ParentalKey(Plan, on_delete=models.CASCADE, related_name='action_schedules')
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


class ActionStatus(models.Model, PlanRelatedModel):
    """The current status for the action ("on time", "late", "completed", etc.)."""
    plan = ParentalKey(
        Plan, on_delete=models.CASCADE, related_name='action_statuses',
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


class ActionImplementationPhase(OrderedModel, PlanRelatedModel):
    plan = ParentalKey(
        Plan, on_delete=models.CASCADE, related_name='action_implementation_phases',
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
        Plan, on_delete=models.CASCADE, related_name='action_decision_levels',
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

    objects = ActionTaskQuerySet.as_manager()

    verbose_name_partitive = pgettext_lazy('partitive', 'action task')

    public_fields = [
        'id', 'action', 'name', 'state', 'comment', 'due_at', 'completed_at', 'created_at', 'modified_at',
    ]

    class Meta:
        ordering = ('action', '-due_at')
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


class ActionImpact(OrderedModel, PlanRelatedModel):
    """An impact classification for an action in an action plan."""

    plan = ParentalKey(
        Plan, on_delete=models.CASCADE, related_name='action_impacts',
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


class CategoryType(ClusterableModel, PlanRelatedModel):
    """Type of the categories.

    Is used to group categories together. One action plan can have several
    category types.
    """

    plan = models.ForeignKey(Plan, on_delete=models.CASCADE, related_name='category_types')
    name = models.CharField(max_length=50, verbose_name=_('name'))
    identifier = IdentifierField()
    usable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('usable for action categorization'),
    )
    usable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('usable for indicator categorization'),
    )
    editable_for_actions = models.BooleanField(
        default=False,
        verbose_name=_('editable for actions'),
    )
    editable_for_indicators = models.BooleanField(
        default=False,
        verbose_name=_('editable for indicators'),
    )

    public_fields = [
        'id', 'plan', 'name', 'identifier', 'editable_for_actions', 'editable_for_indicators',
        'usable_for_indicators', 'usable_for_actions', 'levels', 'categories', 'metadata',
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'name')
        verbose_name = _('category type')
        verbose_name_plural = _('category types')

    def __str__(self):
        return "%s (%s:%s)" % (self.name, self.plan.identifier, self.identifier)


@reversion.register()
class CategoryLevel(OrderedModel):
    """Hierarchy level within a CategoryType.

    Root level has order=0, first child level order=1 and so on.
    """
    type = ParentalKey(
        CategoryType, on_delete=models.CASCADE, related_name='levels',
        verbose_name=_('type')
    )
    name = models.CharField(max_length=100, verbose_name=_('name'))
    name_plural = models.CharField(max_length=100, verbose_name=_('plural name'), null=True, blank=True)
    i18n = TranslationField(fields=('name',))

    public_fields = [
        'id', 'name', 'name_plural', 'order', 'type',
    ]

    class Meta:
        unique_together = (('type', 'order'),)
        verbose_name = _('category level')
        verbose_name_plural = _('category levels')
        ordering = ('type', 'order')

    def __str__(self):
        return self.name


@reversion.register()
class CategoryTypeMetadata(ClusterableModel, OrderedModel):
    class MetadataFormat(models.TextChoices):
        ORDERED_CHOICE = 'ordered_choice', _('Ordered choice')
        RICH_TEXT = 'rich_text', _('Rich text')

    type = ParentalKey(CategoryType, on_delete=models.CASCADE, related_name='metadata')
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))
    format = models.CharField(max_length=50, choices=MetadataFormat.choices, verbose_name=_('Format'))

    public_fields = [
        'identifier', 'name', 'format', 'choices'
    ]

    class Meta:
        unique_together = (('type', 'identifier'), ('type', 'order'))
        verbose_name = _('category metadata')
        verbose_name_plural = _('category metadatas')

    def __str__(self):
        return self.name

    def filter_siblings(self, qs):
        return qs.filter(type=self.type)

    def set_category_value(self, category, val):
        assert category.type == self.type

        if self.format == self.MetadataFormat.ORDERED_CHOICE:
            existing = self.category_choices.filter(category=category)
            if existing:
                existing.delete()
            if val is not None:
                self.category_choices.create(category=category, choice=val)
        elif self.format == self.MetadataFormat.RICH_TEXT:
            obj = self.category_richtexts.filter(category=category).first()
            if not val and obj is not None:
                obj.delete()
                return

            if obj is None:
                obj = CategoryMetadataRichText(metadata=self, category=category)
            obj.text = val
            obj.save()


class CategoryTypeMetadataChoice(OrderedModel):
    metadata = ParentalKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name='choices')
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))

    public_fields = [
        'identifier', 'name'
    ]

    class Meta:
        unique_together = (('metadata', 'identifier'), ('metadata', 'order'),)
        ordering = ('metadata', 'order')
        verbose_name = _('category type metadata choice')
        verbose_name_plural = _('category type metadata choices')

    def __str__(self):
        return self.name


class Category(ClusterableModel, OrderedModel, PlanRelatedModel):
    """A category for actions and indicators."""

    type = models.ForeignKey(
        CategoryType, on_delete=models.PROTECT, related_name='categories',
        verbose_name=_('type')
    )
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))
    image = models.ForeignKey(
        'images.AplansImage', null=True, blank=True, on_delete=models.SET_NULL, related_name='+'
    )
    parent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL, related_name='children',
        verbose_name=_('parent category')
    )
    short_description = models.TextField(
        max_length=200, blank=True, verbose_name=_('short description')
    )
    color = models.CharField(
        max_length=50, blank=True, null=True, verbose_name=_('theme color'),
        help_text=_('Set if the category has a theme color'),
        validators=[validate_css_color]
    )

    i18n = TranslationField(fields=('name', 'short_description'))

    public_fields = [
        'id', 'type', 'order', 'identifier', 'name', 'parent', 'short_description', 'color',
        'children', 'category_page',
    ]

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

            if self.parent.type != self.type:
                raise ValidationError({'parent': _('Parent must be of same type')})

    def get_plans(self):
        return [self.type.plan]

    @classmethod
    def filter_by_plan(cls, plan, qs):
        return qs.filter(type__plan=plan)

    def set_plan(self, plan):
        # The right plan should be set through CategoryType relation, so
        # we do nothing here.
        pass

    def __str__(self):
        if self.identifier and self.identifier[0].isnumeric():
            return "%s %s" % (self.identifier, self.name)
        else:
            return self.name


class CategoryMetadataRichText(models.Model):
    metadata = models.ForeignKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name=_('category_richtexts'))
    category = ParentalKey(Category, on_delete=models.CASCADE, related_name=_('metadata_richtexts'))
    text = RichTextField(verbose_name=_('Text'))

    public_fields = [
        'id', 'metadata', 'category', 'text',
    ]

    class Meta:
        unique_together = ('category', 'metadata')

    def __str__(self):
        return '%s for %s' % (self.metadata, self.category)


class CategoryMetadataChoice(models.Model):
    metadata = models.ForeignKey(CategoryTypeMetadata, on_delete=models.CASCADE, related_name='category_choices')
    category = ParentalKey(Category, on_delete=models.CASCADE, related_name=_('metadata_choices'))
    choice = models.ForeignKey(CategoryTypeMetadataChoice, on_delete=models.CASCADE, related_name=_('categories'))

    class Meta:
        unique_together = ('category', 'metadata')

    def __str__(self):
        return '%s (%s) for %s' % (self.choice, self.metadata, self.category)


class Scenario(models.Model, PlanRelatedModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='scenarios',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = IdentifierField()
    description = models.TextField(null=True, blank=True, verbose_name=_('description'))

    public_fields = [
        'id', 'plan', 'name', 'identifier', 'description',
    ]

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

    public_fields = [
        'id', 'action', 'title', 'date', 'author', 'content', 'created_at', 'modified_at',
    ]

    class Meta:
        verbose_name = _('action status update')
        verbose_name_plural = _('action status updates')
        ordering = ('-date',)

    def __str__(self):
        return '%s – %s – %s' % (self.action, self.created_at, self.title)


class ImpactGroup(models.Model, PlanRelatedModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='impact_groups',
        verbose_name=_('plan')
    )
    name = models.CharField(verbose_name=_('name'), max_length=200)
    identifier = IdentifierField()
    parent = models.ForeignKey(
        'self', on_delete=models.SET_NULL, related_name='children', null=True, blank=True,
        verbose_name=_('parent')
    )
    weight = models.FloatField(verbose_name=_('weight'), null=True, blank=True)
    color = models.CharField(
        max_length=16, verbose_name=_('color'), null=True, blank=True,
        validators=[validate_css_color]
    )

    i18n = TranslationField(fields=('name',))

    public_fields = [
        'id', 'plan', 'identifier', 'parent', 'weight', 'name', 'color', 'actions',
    ]

    class Meta:
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('impact group')
        verbose_name_plural = _('impact groups')
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

    public_fields = [
        'id', 'group', 'action', 'impact',
    ]

    class Meta:
        unique_together = (('group', 'action'),)
        verbose_name = _('impact group action')
        verbose_name_plural = _('impact group actions')

    def __str__(self):
        return "%s ➜ %s" % (self.action, self.group)


class MonitoringQualityPoint(OrderedModel, PlanRelatedModel):
    name = models.CharField(max_length=100, verbose_name=_('name'))
    description_yes = models.CharField(max_length=200, verbose_name=_("description when action fulfills criteria"))
    description_no = models.CharField(max_length=200, verbose_name=_("description when action doesn\'t fulfill criteria"))

    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='monitoring_quality_points',
        verbose_name=_('plan')
    )
    identifier = IdentifierField()

    i18n = TranslationField(fields=('name', 'description_yes', 'description_no'))

    public_fields = [
        'id', 'name', 'description_yes', 'description_no', 'plan', 'identifier',
    ]

    class Meta:
        verbose_name = _('monitoring quality point')
        verbose_name_plural = _('monitoring quality points')
        unique_together = (('plan', 'order'),)
        ordering = ('plan', 'order')

    def __str__(self):
        return self.name
