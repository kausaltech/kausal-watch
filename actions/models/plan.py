import logging
import re

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, RegexValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.core.models import Collection, Site

import reversion

from aplans.utils import ChoiceArrayField, IdentifierField, OrderedModel, PlanRelatedModel, validate_css_color
from orgs.models import Organization

logger = logging.getLogger(__name__)


User = get_user_model()


def get_supported_languages():
    for x in settings.LANGUAGES:
        yield x


def get_default_language():
    return settings.LANGUAGES[0][0]


class PlanQuerySet(models.QuerySet):
    def for_hostname(self, hostname):
        hostname = hostname.lower()

        # Get plan identifier from hostname for development and testing
        parts = hostname.split('.', maxsplit=1)
        if len(parts) == 2 and parts[1] in settings.HOSTNAME_PLAN_DOMAINS:
            return self.filter(identifier=parts[0])

        return self.filter(domains__hostname=hostname.lower())


@reversion.register(follow=[
    'action_statuses', 'action_implementation_phases',  # fixme
])
class Plan(ClusterableModel):
    """The Action Plan under monitoring.

    Most information in this service is linked to a Plan.
    """
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = IdentifierField(unique=True)
    short_name = models.CharField(max_length=50, verbose_name=_('short name'), null=True, blank=True)
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
    show_admin_link = models.BooleanField(
        default=False, verbose_name=_('show admin link'),
        help_text=_('Should the public website contain a link to the admin login?'),
    )
    organization = models.ForeignKey(
        Organization, related_name='plans', on_delete=models.PROTECT, verbose_name=_('main organization for the plan'),
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
    contact_persons_private = models.BooleanField(
        default=False, verbose_name=_('Contact persons private'),
        help_text=_('Set if the contact persons should not be visible in the public UI')
    )
    hide_action_identifiers = models.BooleanField(
        default=False, verbose_name=_('Hide action identifiers'),
        help_text=_("Set if the plan doesn't have meaningful action identifiers")
    )
    hide_action_official_name = models.BooleanField(
        default=False, verbose_name=_('Hide official name field'),
        help_text=_("Set if the plan doesn't use the official name field")
    )
    hide_action_lead_paragraph = models.BooleanField(
        default=True, verbose_name=_('Hide lead paragraph'),
        help_text=_("Set if the plan doesn't use the lead paragraph field")
    )
    has_action_primary_orgs = models.BooleanField(
        default=False, verbose_name=_('Has primary organisations for actions'),
        help_text=_("Set if actions have a clear primary organisation")
    )

    related_organizations = models.ManyToManyField(Organization, blank=True, related_name='related_plans')
    related_plans = models.ManyToManyField('self', blank=True)

    cache_invalidated_at = models.DateTimeField(auto_now=True)
    i18n = TranslationField(fields=['name', 'short_name'])

    public_fields = [
        'id', 'name', 'short_name', 'identifier', 'image', 'action_schedules',
        'actions', 'category_types', 'action_statuses', 'indicator_levels',
        'action_impacts', 'general_content', 'impact_groups',
        'monitoring_quality_points', 'scenarios',
        'primary_language', 'other_languages', 'accessibility_statement_url',
        'action_implementation_phases', 'hide_action_identifiers', 'hide_action_official_name',
        'hide_action_lead_paragraph', 'organization',
        'related_plans',
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
        all_related = self.related_organizations.all()
        for org in self.related_organizations.all():
            all_related |= org.get_descendants()
        if self.organization:
            all_related |= Organization.objects.filter(id=self.organization.id)
            all_related |= self.organization.get_descendants()
        return all_related.distinct()

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
            root_page = self.create_pages()
            site = Site(site_name=self.name, hostname=self.site_url, root_page=root_page)
            site.save()
            self.site = site
            update_fields.append('site')
        else:
            # FIXME: Update Site and PlanRootPage attributes
            pass

        group_name = '%s admins' % self.name
        if self.admin_group is None:
            obj = Group.objects.create(name=group_name)
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

    def create_pages(self):
        """Create plan root page as well as subpages that should be always there and return plan root page."""
        from wagtail.core.models import Page

        from pages.models import ActionListPage, IndicatorListPage, PlanRootPage

        root_pages = Page.get_first_root_node().get_children().type(PlanRootPage)
        try:
            root_page = root_pages.get(slug=self.identifier)
        except Page.DoesNotExist:
            root_page = Page.get_first_root_node().add_child(
                instance=PlanRootPage(title=self.name, slug=self.identifier, url_path='')
            )
        action_list_pages = root_page.get_children().type(ActionListPage)
        if not action_list_pages.exists():
            root_page.add_child(instance=ActionListPage(title=_("Actions")))
        indicator_list_pages = root_page.get_children().type(IndicatorListPage)
        if not indicator_list_pages.exists():
            root_page.add_child(instance=IndicatorListPage(title=_("Indicators")))
        return root_page


def is_valid_hostname(hostname):
    if len(hostname) > 255:
        return False
    allowed = re.compile("(?!-)[A-Z\d-]{1,63}(?<!-)$", re.IGNORECASE)
    return all(allowed.match(x) for x in hostname.split("."))


class PlanDomain(models.Model):
    """A domain (hostname) where an UI for a Plan might live."""

    plan = ParentalKey(
        Plan, on_delete=models.CASCADE, related_name='domains', verbose_name=_('plan')
    )
    hostname = models.CharField(
        max_length=200, verbose_name=_('host name'), db_index=True,
        validators=[is_valid_hostname]
    )
    base_path = models.CharField(
        max_length=200, verbose_name=_('base path'), null=True, blank=True,
        validators=[RegexValidator(
            regex=r'^\/[a-z_-]+',
            message=_("Base path must begin with a '/' and not end with '/'")
        )],
    )
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
        unique_together = (('hostname', 'base_path'),)


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


class MonitoringQualityPoint(OrderedModel, PlanRelatedModel):
    name = models.CharField(max_length=100, verbose_name=_('name'))
    description_yes = models.CharField(
        max_length=200,
        verbose_name=_("description when action fulfills criteria")
    )
    description_no = models.CharField(
        max_length=200,
        verbose_name=_("description when action doesn\'t fulfill criteria")
    )

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
