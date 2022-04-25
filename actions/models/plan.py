from __future__ import annotations

import typing
from typing import Optional, Tuple, Type, Union
import logging
import re
from urllib.parse import urlparse

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.validators import URLValidator, RegexValidator
from django.db import models, transaction
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from wagtail.core.models import Collection, Page, Site
from wagtail.core.models.i18n import Locale

import reversion

from aplans.utils import ChoiceArrayField, IdentifierField, OrderedModel, PlanRelatedModel, validate_css_color
from orgs.models import Organization
from people.models import Person

if typing.TYPE_CHECKING:
    from .features import PlanFeatures
    from .action import ActionStatus, ActionImplementationPhase
    from .category import CategoryType
    from django.db.models.manager import RelatedManager


logger = logging.getLogger(__name__)


User = get_user_model()


def get_supported_languages():
    for x in settings.LANGUAGES:
        yield x


def get_default_language():
    return settings.LANGUAGES[0][0]


def get_plan_identifier_from_wildcard_domain(hostname: str) -> Union[Tuple[str, str], Tuple[None, None]]:
    # Get plan identifier from hostname for development and testing
    parts = hostname.split('.', maxsplit=1)
    if len(parts) == 2 and parts[1].lower() in settings.HOSTNAME_PLAN_DOMAINS:
        return (parts[0], parts[1])
    else:
        return (None, None)


class PlanQuerySet(models.QuerySet):
    def for_hostname(self, hostname):
        hostname = hostname.lower()
        # Get plan identifier from hostname for development and testing
        identifier, _ = get_plan_identifier_from_wildcard_domain(hostname)
        if identifier:
            return self.filter(identifier=identifier)
        return self.filter(domains__hostname=hostname)

    def live(self):
        return self.filter(published_at__isnull=False, archived_at__isnull=True)


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
    published_at = models.DateTimeField(null=True, verbose_name=_('published at'))
    archived_at = models.DateTimeField(null=True, verbose_name=_('archived at'))
    site_url = models.URLField(
        blank=True, null=True, verbose_name=_('site URL'),
        validators=[URLValidator(('http', 'https'))]
    )
    actions_locked = models.BooleanField(
        default=False, verbose_name=_('actions locked'),
        help_text=_('Can actions be added and the official metadata edited?'),
    )
    organization = models.ForeignKey(
        Organization, related_name='plans', on_delete=models.PROTECT, verbose_name=_('main organization for the plan'),
    )

    general_admins = models.ManyToManyField(
        Person, blank=True, related_name='general_admin_plans', through='GeneralPlanAdmin',
        verbose_name=_('general administrators'),
        help_text=_('Persons that can modify everything related to the action plan')
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
    theme_identifier = IdentifierField(verbose_name=_('Theme identifier'), null=True, blank=True)

    related_organizations = models.ManyToManyField(Organization, blank=True, related_name='related_plans')
    related_plans = models.ManyToManyField('self', blank=True)

    features: PlanFeatures
    action_statuses: RelatedManager[ActionStatus]
    action_implementation_phases: RelatedManager[ActionImplementationPhase]
    category_types: RelatedManager[CategoryType]
    domains: RelatedManager[PlanDomain]

    cache_invalidated_at = models.DateTimeField(auto_now=True)
    i18n = TranslationField(fields=['name', 'short_name'])

    public_fields = [
        'id', 'name', 'short_name', 'identifier', 'image', 'action_schedules',
        'actions', 'category_types', 'action_statuses', 'indicator_levels',
        'action_impacts', 'general_content', 'impact_groups',
        'monitoring_quality_points', 'scenarios',
        'primary_language', 'other_languages', 'accessibility_statement_url',
        'action_implementation_phases', 'organization',
        'related_plans', 'theme_identifier',
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

    def get_related_organizations(self) -> models.QuerySet[Organization]:
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

    def get_translated_root_page(self):
        """Return root page in activated language, fall back to default language."""
        root = self.root_page
        language = translation.get_language()
        try:
            locale = Locale.objects.get(language_code=language)
            root = root.get_translation(locale)
        except (Locale.DoesNotExist, Page.DoesNotExist):
            pass
        return root

    def save(self, *args, **kwargs):
        PlanFeatures: Type[PlanFeatures] = apps.get_model('actions', 'PlanFeatures')

        ret = super().save(*args, **kwargs)

        update_fields = []
        if self.root_collection is None:
            with transaction.atomic():
                obj = Collection.get_first_root_node().add_child(name=self.name)
            self.root_collection = obj
            update_fields.append('root_collection')
        else:
            if self.root_collection.name != self.name:
                self.root_collection.name = self.name
                self.root_collection.save(update_fields=['name'])

        if self.site is None:
            root_page = self.create_default_pages()
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

        if not PlanFeatures.objects.filter(plan=self).exists():
            PlanFeatures.objects.create(plan=self)

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

    def create_default_pages(self):
        """Create plan root page as well as subpages that should be always there and return plan root page."""
        from pages.models import ActionListPage, IndicatorListPage, PlanRootPage

        locale = Locale.objects.get(language_code=self.primary_language)
        root_pages = Page.get_first_root_node().get_children().type(PlanRootPage)
        try:
            root_page = root_pages.get(slug=self.identifier)
        except Page.DoesNotExist:
            root_page = Page.get_first_root_node().add_child(
                instance=PlanRootPage(title=self.name, slug=self.identifier, url_path='', locale=locale)
            )

        with translation.override(self.primary_language):
            action_list_pages = root_page.get_children().type(ActionListPage)
            if not action_list_pages.exists():
                root_page.add_child(instance=ActionListPage(title=_("Actions"), locale=locale))
            indicator_list_pages = root_page.get_children().type(IndicatorListPage)
            if not indicator_list_pages.exists():
                root_page.add_child(instance=IndicatorListPage(title=_("Indicators"), locale=locale))

        return root_page

    def is_live(self):
        return self.published_at is not None and self.archived_at is None

    def get_view_url(self, client_url: Optional[str] = None) -> str:
        """Return an URL for the homepage of the plan.

        If `client_url` is given, try to return the URL that matches the supplied
        `client_url` the best:
          1. If `client_url` is from a wildcard domain, return the hostname that
             matches the wildcard (with matching protocol and port).
          2. Otherwise, see if the plan has a PlanDomain matching the hostname
             (possibly with a URL path prefix).
          3. If not, return the main URL.
        """
        port = hostname = scheme = None
        if client_url:
            parts = urlparse(client_url)
            hostname = parts.netloc.split(':')[0]
            scheme = parts.scheme
            if scheme not in ('https', 'http'):
                raise Exception('Invalid scheme in client_url')
            port = parts.port
            if scheme == 'https' and port == 443:
                port = None
            elif scheme == 'http' and port == 80:
                port = None

        base_path = None
        if hostname:
            _, wildcard_hostname = get_plan_identifier_from_wildcard_domain(hostname)
            if wildcard_hostname:
                hostname = '%s.%s' % (self.identifier, wildcard_hostname)
                base_path = '/'
            else:
                domains = self.domains.all()
                for domain in domains:
                    if domain.hostname == hostname:
                        hostname = domain.hostname
                        base_path = domain.base_path or '/'
                        break
                else:
                    hostname = None

        if hostname:
            if not scheme:
                scheme = 'https'
            if not base_path:
                base_path = ''
            else:
                base_path = base_path.rstrip('/')
            if port:
                port_str = ':%s' % port
            else:
                port_str = ''
            return '%s://%s%s%s' % (scheme, hostname, port_str, base_path)
        else:
            if self.site_url.startswith('http'):
                url = self.site_url.rstrip('/')
            else:
                url = 'https://%s' % self.site_url
            return url

    @classmethod
    @transaction.atomic()
    def create_with_defaults(
        self, identifier: str, name: str, primary_language: str, organization: Organization,
        other_languages: typing.List[str] = [],
        short_name: str = None, base_path: str = None, domain: str = None,
        client_identifier: str = None, client_name: str = None, azure_ad_tenant_id: str = None
    ) -> Plan:
        from ..defaults import (
            DEFAULT_ACTION_IMPLEMENTATION_PHASES, DEFAULT_ACTION_STATUSES
        )
        plan = Plan(
            identifier=identifier,
            name=name,
            primary_language=primary_language,
            organization=organization,
            other_languages=other_languages
        )
        default_domains = [x for x in settings.HOSTNAME_PLAN_DOMAINS if x != 'localhost']
        if not domain:
            if not default_domains:
                raise Exception("site_url not provided and no default domains configured")
            domain = default_domains[0]
            site_url = 'https://%s.%s' % (identifier, domain)
        else:
            site_url = 'https://%s' % domain
        if base_path:
            site_url += '/' + base_path.strip('/')
        plan.site_url = site_url
        plan.statuses_updated_manually = True
        if short_name:
            plan.short_name = short_name
        plan.save()

        with translation.override(plan.primary_language):
            from actions.models import ActionStatus, ActionImplementationPhase

            for st in DEFAULT_ACTION_STATUSES:
                obj = ActionStatus(
                    plan=plan, identifier=st['identifier'], name=st['name'],
                    is_completed=st.get('is_completed', False)
                )
                obj.save()

            for idx, st in enumerate(DEFAULT_ACTION_IMPLEMENTATION_PHASES):
                obj = ActionImplementationPhase(
                    plan=plan, order=idx, identifier=st['identifier'], name=st['name'],
                )
                obj.save()

        if client_name:
            from admin_site.models import Client, AdminHostname

            client = Client.objects.filter(name=client_name).first()
            if client is None:
                client = Client.objects.create(name=client_name)
            if azure_ad_tenant_id:
                client.azure_ad_tenant_id = azure_ad_tenant_id
                client.save()

            if settings.ADMIN_WILDCARD_DOMAIN and client_identifier:
                hostname = '%s.%s' % (client_identifier, settings.ADMIN_WILDCARD_DOMAIN)
                hn_obj = AdminHostname.objects.filter(client=client, hostname=hostname).first()
                if hn_obj is None:
                    AdminHostname.objects.create(client=client, hostname=hostname)

        return plan

# ParentalManyToManyField  won't help, so we need the through model:
# https://stackoverflow.com/questions/49522577/how-to-choose-a-wagtail-image-across-a-parentalmanytomanyfield
# Unfortunately the reverse accessors then point to instances of the through model, not the actual target.
class GeneralPlanAdmin(OrderedModel):
    plan = ParentalKey(Plan, on_delete=models.CASCADE, verbose_name=_('plan'), related_name='general_admins_ordered')
    person = models.ForeignKey(Person, on_delete=models.CASCADE, verbose_name=_('person'),
                               related_name='general_admin_plans_ordered')

    class Meta:
        ordering = ['plan', 'order']
        index_together = (('plan', 'order'),)
        unique_together = (('plan', 'person',),)
        verbose_name = _('general plan admin')
        verbose_name_plural = _('general plan admins')

    def __str__(self):
        return str(self.person)


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
        s = str(self.hostname)
        if self.base_path:
            s += ':' + self.base_path
        return s

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
