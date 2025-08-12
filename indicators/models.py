from __future__ import annotations

import datetime
import typing
import uuid
from typing import TYPE_CHECKING, Any, Callable, ClassVar, Self, cast

import reversion
from django.apps import apps
from django.contrib.admin import display
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q, QuerySet
from django.db.models.functions import Collate
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.manager import MultilingualQuerySet
from wagtail.fields import RichTextField
from wagtail.search import index
from wagtail.search.queryset import SearchableQuerySetMixin

from dateutil.relativedelta import relativedelta
from wagtail_color_panel.fields import ColorField

from kausal_common.models.types import (
    MLModelManager,
    ModelManager,
    manager_from_mlqs,
)

from aplans import utils
from aplans.utils import (
    AdminSaveContext,
    IdentifierField,
    ModificationTracking,
    OrderedModel,
    PlanDefaultsModel,
    RestrictedVisibilityModel,
    TranslatedModelMixin,
    get_available_variants_for_language,
)

from actions.models.features import OrderBy
from orgs.models import Organization
from search.backends import TranslatedAutocompleteField, TranslatedSearchField

if typing.TYPE_CHECKING:
    from modelcluster.fields import PK

    from kausal_common.models.types import FK, M2M, MLMM, RevMany
    from kausal_common.users import UserOrAnon

    from actions.models import Action
    from actions.models.category import Category, CategoryType
    from actions.models.plan import Plan, PlanQuerySet
    from people.models import Person


User = get_user_model()


def latest_plan():
    PlanModel = cast('Plan', apps.get_model('actions', 'Plan'))
    if PlanModel.objects.exists():
        return PlanModel.objects.latest()
    return None


@reversion.register
class Quantity(ClusterableModel, TranslatedModelMixin, ModificationTracking):
    """The quantity that an indicator measures."""

    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)

    i18n = TranslationField(fields=['name'])

    autocomplete_search_field = 'name'

    objects: ClassVar[MLMM[Self, MultilingualQuerySet[Self]]] = manager_from_mlqs(MultilingualQuerySet[Self])

    # type annotations
    indicators: RevMany[Indicator]
    common_indicators: RevMany[CommonIndicator]

    class Meta:
        verbose_name = pgettext_lazy('physical', 'quantity')
        verbose_name_plural = pgettext_lazy('physical', 'quantities')
        ordering = ('name',)

    def __str__(self):
        return self.get_i18n_value('name')

    def autocomplete_label(self):
        return str(self)


@reversion.register()
class Unit(ClusterableModel, ModificationTracking):
    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)
    short_name = models.CharField(
        max_length=40, null=True, blank=True,
        verbose_name=_('short name'),
    )
    verbose_name = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=_('verbose name'),
    )
    verbose_name_plural = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=_('verbose name plural'),
    )

    i18n = TranslationField(
        fields=['name', 'short_name', 'verbose_name', 'verbose_name_plural'],
    )

    objects: ClassVar[MLMM[Self, MultilingualQuerySet[Self]]] = manager_from_mlqs(MultilingualQuerySet[Self])

    autocomplete_search_field = 'name'

    # type annotations
    indicators: RevMany[Indicator]
    common_indicators: RevMany[CommonIndicator]
    name_i18n: str
    short_name_i18n: str
    verbose_name_i18n: str
    verbose_name_plural_i18n: str

    class Meta:
        verbose_name = _('unit')
        verbose_name_plural = _('units')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def autocomplete_label(self):
        return str(self)


class DatasetLicense(models.Model):
    name = models.CharField(max_length=50, verbose_name=_('name'), unique=True)

    class Meta:
        verbose_name = _('dataset license')
        verbose_name_plural = _('dataset licenses')

    def __str__(self):
        return self.name


class Dataset(ClusterableModel):
    name = models.CharField(max_length=100, verbose_name=_('name'))
    description = models.TextField(blank=True, verbose_name=_('description'))
    url = models.URLField(null=True, blank=True, verbose_name=_('URL'))
    last_retrieved_at = models.DateField(
        null=True, blank=True, verbose_name=_('last retrieved at'),
    )
    owner = models.ForeignKey(
        Organization, null=True, blank=True, verbose_name=_('owner'), on_delete=models.SET_NULL,
    )
    owner_name = models.CharField(
        max_length=100, null=True, blank=True, verbose_name=_('owner name'),
        help_text=_('Set if owner organization is not available'),
    )
    license = models.ForeignKey(
        DatasetLicense, null=True, blank=True, verbose_name=_('license'),
        on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = _('dataset')
        verbose_name_plural = _('datasets')

    def __str__(self):
        return self.name


class Framework(ClusterableModel):
    identifier = IdentifierField(unique=True)
    name = models.CharField(max_length=200, verbose_name=_('name'))

    i18n = TranslationField(fields=['name'])

    public_fields: ClassVar = ['id', 'name']

    class Meta:
        verbose_name = _('framework')
        verbose_name_plural = _('frameworks')

    def __str__(self):
        return self.name


class IndicatorRelationship(models.Model):
    """A causal relationship between two indicators."""

    INCREASES = 'increases'
    DECREASES = 'decreases'
    PART_OF = 'part_of'

    EFFECT_TYPES = (
        (INCREASES, _('increases')),
        (DECREASES, _('decreases')),
        (PART_OF, _('is a part of')),
    )
    effect_type = models.CharField(
        max_length=40, choices=EFFECT_TYPES,
        verbose_name=_('effect type'), help_text=_('What type of causal effect is there between the indicators'))

    class Meta:
        abstract = True

    causal_indicator: Any
    effect_indicator: Any

    def __str__(self):
        return "%s %s %s" % (self.causal_indicator, self.effect_type, self.effect_indicator)  # type: ignore


@reversion.register()
class CommonIndicator(ClusterableModel):
    identifier = IdentifierField[str | None](null=True, blank=True, max_length=70)
    name = models.CharField(max_length=200, verbose_name=_('name'))
    description = RichTextField[str | None, str | None](null=True, blank=True, verbose_name=_('description'))

    quantity = ParentalKey(
        Quantity, related_name='common_indicators', on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'),
    )
    unit = ParentalKey(
        Unit, related_name='common_indicators', on_delete=models.PROTECT,
        verbose_name=_('unit'),
    )
    plans: M2M[Plan, PlanCommonIndicator] = models.ManyToManyField(
        'actions.Plan', blank=True, related_name='common_indicators', through='PlanCommonIndicator',
    )
    normalization_indicators: M2M[Self, CommonIndicatorNormalizator] = models.ManyToManyField(
        'self', blank=True, related_name='normalizable_indicators', symmetrical=False,
        through='CommonIndicatorNormalizator', through_fields=('normalizable', 'normalizer'),
    )
    normalize_by_label = models.CharField(
        max_length=200, verbose_name=_('normalize by label'), null=True, blank=True,
    )

    i18n = TranslationField(fields=['name', 'description', 'normalize_by_label'])

    public_fields: ClassVar = [
        'id', 'identifier', 'name', 'description', 'quantity', 'unit',
        'indicators', 'dimensions', 'related_causes', 'related_effects',
        'normalization_indicators', 'normalize_by_label', 'normalizations',
    ]

    normalizations: RevMany[CommonIndicatorNormalizator]
    indicators: RevMany[Indicator]

    class Meta:
        verbose_name = _('common indicator')
        verbose_name_plural = _('common indicators')

    def __str__(self):
        return self.name

    def autocomplete_label(self):
        return str(self)


class CommonIndicatorNormalizator(models.Model):
    normalizable = models.ForeignKey(CommonIndicator, on_delete=models.CASCADE, related_name='normalizations')
    normalizer = models.ForeignKey(CommonIndicator, on_delete=models.CASCADE, related_name='+')
    unit = models.ForeignKey(Unit, on_delete=models.PROTECT, related_name='+')
    unit_multiplier = models.FloatField()

    class Meta:
        unique_together = (('normalizable', 'normalizer'),)

    def __str__(self) -> str:
        return "'%s' normalized by '%s'" % (self.normalizable, self.normalizer)


class PlanCommonIndicator(models.Model):
    common_indicator = models.ForeignKey(CommonIndicator, on_delete=models.CASCADE, related_name='+')
    plan = models.ForeignKey('actions.Plan', on_delete=models.CASCADE, related_name='+')

    def __str__(self):
        return '%s in %s' % (self.common_indicator, self.plan)


class RelatedCommonIndicator(IndicatorRelationship):
    causal_indicator = models.ForeignKey(
        CommonIndicator, related_name='related_effects', on_delete=models.CASCADE,
        verbose_name=_('causal indicator'),
    )
    effect_indicator = models.ForeignKey(
        CommonIndicator, related_name='related_causes', on_delete=models.CASCADE,
        verbose_name=_('effect indicator'),
    )

    public_fields: typing.ClassVar = ['id', 'causal_indicator', 'effect_indicator', 'effect_type']

    class Meta:
        unique_together = (('causal_indicator', 'effect_indicator'),)
        verbose_name = _('related indicator')
        verbose_name_plural = _('related indicators')


class FrameworkIndicator(models.Model):
    identifier = IdentifierField[str | None](null=True, blank=True, max_length=70)
    common_indicator = ParentalKey(
        CommonIndicator, related_name='frameworks', on_delete=models.CASCADE,
        verbose_name=_('common indicator'),
    )
    framework = ParentalKey(
        Framework, related_name='common_indicators', on_delete=models.CASCADE,
        verbose_name=_('framework'),
    )

    public_fields: ClassVar = ['id', 'identifier', 'common_indicator', 'framework']

    class Meta:
        verbose_name = _('framework indicator')
        verbose_name_plural = _('framework indicators')

    def __str__(self):
        return '%s ∈ %s' % (str(self.common_indicator), str(self.framework))


class IndicatorQuerySet(SearchableQuerySetMixin, MultilingualQuerySet['Indicator']):
    def available_for_plan(self, plan: Plan):
        related_orgs = Organization.objects.qs.available_for_plan(plan)
        return self.filter(organization__in=related_orgs)

    def visible_for_user(self, user: UserOrAnon | None) -> Self:
        """
        Filter by visibility for a specific user.

        A None value is interpreted identically to a non-authenticated user
        """
        if user is None or not user.is_authenticated:
            return self.filter(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        return self

    def visible_for_public(self) -> Self:
        return self.visible_for_user(None)


if TYPE_CHECKING:
    class IndicatorManager(MLModelManager['Indicator', IndicatorQuerySet]):
        pass
else:
    IndicatorManager = MLModelManager.from_queryset(IndicatorQuerySet)


@reversion.register(follow=('goals',))
class Indicator(ClusterableModel, index.Indexed, ModificationTracking, PlanDefaultsModel, RestrictedVisibilityModel):
    """An indicator with which to measure actions and progress towards strategic goals."""

    TIME_RESOLUTIONS = (
        ('year', _('year')),
        ('month', _('month')),
        ('day', _('day')),
    )
    LEVELS = (
        ('strategic', _('strategic')),
        ('tactical', _('tactical')),
        ('operational', _('operational')),
    )

    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    common = models.ForeignKey(
        CommonIndicator, null=True, blank=True, related_name='indicators',
        on_delete=models.PROTECT, verbose_name=_('common indicator'),
    )
    organization = models.ForeignKey(
        Organization, related_name='indicators', on_delete=models.CASCADE,
        verbose_name=_('organization'),
    )
    plans: M2M[Plan, IndicatorLevel] = models.ManyToManyField(
        'actions.Plan', through='indicators.IndicatorLevel', blank=True,
        verbose_name=_('plans'), related_name='indicators',
    )
    identifier = IdentifierField[str | None](null=True, blank=True, max_length=70)
    name = models.CharField(max_length=200, verbose_name=_('name'))
    quantity = ParentalKey(
        Quantity, related_name='indicators', on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'), null=True, blank=True,
    )
    unit = ParentalKey(
        Unit, related_name='indicators', on_delete=models.PROTECT,
        verbose_name=_('unit'),
    )
    min_value = models.FloatField(
        null=True, blank=True, verbose_name=_('minimum value'),
        help_text=_("Used in visualizations as the Y axis minimum"),
    )
    max_value = models.FloatField(
        null=True, blank=True, verbose_name=_('maximum value'),
        help_text=_("Used in visualizations as the Y axis maximum"),
    )
    description = RichTextField[str | None, str | None](null=True, blank=True, verbose_name=_('description'))
    categories: M2M[Category, Any] = models.ManyToManyField(
        'actions.Category', blank=True, related_name='indicators',
        through='indicators.IndicatorCategoryThrough',
    )
    time_resolution = models.CharField(
        max_length=50, choices=TIME_RESOLUTIONS, default=TIME_RESOLUTIONS[0][0],
        verbose_name=_('time resolution'),
    )
    updated_values_due_at = models.DateField(null=True, blank=True, verbose_name=_('updated values due at'))
    latest_graph = models.ForeignKey(
        'IndicatorGraph', null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False,
    )
    latest_value = models.ForeignKey(
        'IndicatorValue', null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False,
    )
    datasets: M2M[Dataset, Any] = models.ManyToManyField(
        Dataset, blank=True, verbose_name=_('datasets'),
    )

    # summaries = models.JSONField(null=True)
    # E.g.:
    # {
    #    "day_when_target_reached": "2079-01-22",
    #    "yearly_ghg_emission_reductions_left": "1963000",
    # }

    contact_persons_unordered: M2M[Person, Any] = models.ManyToManyField(
        'people.Person', through='indicators.IndicatorContactPerson', blank=True,
        related_name='contact_for_indicators', verbose_name=_('contact persons'),
    )
    contact_persons: RevMany[IndicatorContactPerson]

    internal_notes = models.TextField(
        blank=True, null=True, verbose_name=_('internal notes'),
    )

    reference = RichTextField[str | None, str | None](
        blank=True, null=True, verbose_name=_('reference'), max_length=255,
        help_text=_("What is the reference or source for this indicator?"),
        features=['link'],
    )

    show_trendline = models.BooleanField(
        default=True, verbose_name=_('show trend line'),
        help_text=_("Automatically create a trend line for the indicator's total value"),
    )

    desired_trend = models.CharField(
        blank=True, null=False, verbose_name=_('desired trend'), max_length=20, default='',
        choices=(
            ('increasing', _('increasing')),
            ('decreasing', _('decreasing')),
            ('', _('attempt to detect automatically')),
        ),
        help_text=_(
            "Which trend in the numerical values of this indicator's goals indicates improvement: when the values are "
            "increasing or decreasing?",
        ),
    )

    show_total_line = models.BooleanField(
        default=True, verbose_name=_('show total line'),
        help_text=_("Data categories can be summed to form total for the indicator (draw stacked chart as default)"),
    )

    ticks_count = models.PositiveIntegerField(blank=True, null=True, help_text=_("Number of steps on the y-axis"))
    ticks_rounding = models.PositiveIntegerField(
        blank=True, null=True, help_text=_("Number of significant digits on y-axis ticks")
    )
    value_rounding = models.PositiveIntegerField(
        blank=True, null=True, help_text=_("Number of significant digits when displaying indicator values")
    )
    data_categories_are_stackable = models.BooleanField(
        default=False,
        help_text=_("Data categories can be summed to form a total for the indicator (draw a stacked chart as default)"),
    )

    sent_notifications = GenericRelation('notifications.SentNotification', related_query_name='indicator')

    i18n = TranslationField(fields=['name', 'description'], default_language_field='organization__primary_language_lowercase')

    search_fields = [
        TranslatedSearchField('name', boost=10),
        TranslatedAutocompleteField('name'),
        TranslatedSearchField('description'),
        index.FilterField('plans'),
        index.FilterField('visibility'),
    ]

    public_fields: ClassVar = [
        'id', 'uuid', 'common', 'organization', 'identifier', 'name', 'quantity', 'unit', 'description',
        'min_value', 'max_value', 'categories', 'time_resolution', 'latest_value', 'latest_graph',
        'datasets', 'updated_at', 'created_at', 'values', 'plans', 'goals', 'related_actions', 'actions',
        'related_causes', 'related_effects', 'dimensions', 'reference', 'show_trendline', 'desired_trend',
        'show_total_line', 'ticks_count', 'ticks_rounding', 'value_rounding', 'data_categories_are_stackable',
    ]

    wagtail_reference_index_ignore = True

    objects: ClassVar[IndicatorManager] = IndicatorManager()

    # type annotations
    id: int
    levels: RevMany[IndicatorLevel]
    values: RevMany[IndicatorValue]
    actions: RevMany[Action]
    related_actions: RevMany[ActionIndicator]
    related_causes: RevMany[RelatedIndicator]
    related_effects: RevMany[RelatedIndicator]
    goals: RevMany[IndicatorGoal]
    latest_value_id: int | None
    name_i18n: str
    description_i18n: str
    dimensions: RevMany[IndicatorDimension]

    class Meta:
        verbose_name = _('indicator')
        verbose_name_plural = _('indicators')
        unique_together = (('common', 'organization'),)
        ordering = ('-updated_at',)

    def handle_admin_save(self, context: AdminSaveContext):
        for rel_action in self.related_actions.get_queryset().all():
            rel_action.action.recalculate_status()

    def get_plans_with_access(self):
        from actions.models import Plan
        plan_qs = self.plans.all()
        return (
            plan_qs |
            # For unconnected indicators, allow seeing and
            # connecting them for plan admins for plans
            # with same organization as indicator organization
            Plan.objects.filter(organization=self.organization)
        )

    def get_level_for_plan(self, plan):
        level = self.levels.filter(plan=plan).first()
        return level.level if level is not None else None

    def initialize_plan_defaults(self, plan):
        self.organization = plan.organization

    def handle_values_update(self):
        update_fields = []

        try:
            latest_value = self.values.filter(categories__isnull=True).latest()
        except IndicatorValue.DoesNotExist:
            latest_value = None

        if self.latest_value != latest_value:
            self.latest_value = latest_value
            update_fields.append('latest_value')

        if self.updated_values_due_at is not None:
            # If latest_value is newer than updated_values_due_at - 1 year, add 1 year to updated_values_due_at
            reporting_period_start = self.updated_values_due_at - relativedelta(years=1)
            if latest_value is not None and latest_value.date >= reporting_period_start:
                self.updated_values_due_at += relativedelta(years=1)
                update_fields.append('updated_values_due_at')

        if self.common is not None:
            for normalizator in self.common.normalizations.all():
                self.generate_normalized_values(normalizator)
            # Also update indicators that normalize by this indicator
            # TODO: Ideally we should check for cycles, but they wouldn't make sense semantically anyway
            for normalizator in CommonIndicatorNormalizator.objects.filter(normalizer=self.common):
                affected_indicators = normalizator.normalizable.indicators.filter(organization=self.organization)
                for indicator in affected_indicators:
                    indicator.generate_normalized_values(normalizator)

        self.save(update_fields=update_fields)

    def handle_goals_update(self):
        if self.common is not None:
            for normalizator in self.common.normalizations.all():
                self.generate_normalized_goals(normalizator)
            # Also update indicators that normalize by this indicator
            # TODO: Ideally we should check for cycles, but they wouldn't make sense semantically anyway
            for normalizator in CommonIndicatorNormalizator.objects.filter(normalizer=self.common):
                affected_indicators = normalizator.normalizable.indicators.filter(organization=self.organization)
                for indicator in affected_indicators:
                    indicator.generate_normalized_goals(normalizator)

    def has_current_data(self):
        return self.latest_value_id is not None

    def has_current_goals(self):
        now = timezone.now()
        return self.goals.filter(date__gte=now).exists()

    @display(boolean=True, description=_('Has datasets'))
    def has_datasets(self):
        return self.datasets.exists()

    @display(boolean=True, description=_('Has data'))
    def has_data(self):
        return self.latest_value_id is not None

    def get_notification_context(self, plan):
        edit_values_url = reverse('indicators_indicator_modeladmin_edit_values', kwargs=dict(instance_pk=self.id))
        return {
            'id': self.id,
            'name': self.name,
            'edit_values_url': edit_values_url,
            'updated_at': self.updated_at,
            'updated_values_due_at': self.updated_values_due_at,
            'view_url': self.get_view_url(plan),
        }

    def get_view_url(self, plan: Plan | None = None, client_url: str | None = None) -> str:
        if plan is None:
            plan = self.plans.first()
        assert plan is not None
        return '%s/indicators/%s' % (plan.get_view_url(client_url=client_url, active_locale=translation.get_language()), self.id)

    def clean(self):
        if self.updated_values_due_at:
            if self.time_resolution != 'year':
                raise ValidationError({'updated_values_due_at':
                                       _('Deadlines for value updates are currently only possible for yearly '
                                         'indicators')})
            if (self.latest_value is not None
                    and self.updated_values_due_at <= self.latest_value.date + relativedelta(years=1)):
                raise ValidationError({'updated_values_due_at':
                                       _('There is already an indicator value for the year preceding the deadline')})

        if self.common:
            if self.common.quantity != self.quantity:
                raise ValidationError({'quantity': _("Quantity must be the same as in common indicator (%s)"  # noqa: INT003
                                                     % self.common.quantity)})
            if self.common.unit != self.unit:
                raise ValidationError({'unit': _("Unit must be the same as in common indicator (%s)"  # noqa: INT003
                                                 % self.common.unit)})
            # Unfortunately it seems we need to check whether dimensions are equal in the form

    def set_categories(self, ctype: CategoryType | str, categories: list[int | Category], plan: Plan | None = None):
        if plan is None:
            plan = self.plans.first()
        assert plan, "No default plan found."
        if isinstance(ctype, str):
            ctype = plan.category_types.get(identifier=ctype)
        all_cats = {x.id: x for x in ctype.categories.all()}
        existing_cats = set(self.categories.filter(type=ctype))
        new_cats: set[Category] = set()
        for cat in categories:
            cat_obj = all_cats[cat] if isinstance(cat, int) else cat
            new_cats.add(cat_obj)

        for cat in existing_cats - new_cats:
            self.categories.remove(cat)
        for cat in new_cats - existing_cats:
            self.categories.add(cat)

    def set_contact_persons(self, data: list[dict[str, Any]]):
        existing_persons = {p.person for p in self.contact_persons.all()}
        new_persons = {d['person'] for d in data}
        IndicatorContactPerson.objects.filter(
            indicator=self, person__in=(existing_persons - new_persons),
        ).delete()
        for d in data:
            IndicatorContactPerson.objects.update_or_create(
                indicator=self,
                person_id=d['person'],
            )


    def generate_normalized_values(self, cin: CommonIndicatorNormalizator):
        assert cin.normalizable == self.common
        nci = cin.normalizer

        ni = Indicator.objects.filter(common=nci, organization=self.organization).first()
        if not ni:
            return

        # Generate only for non-categorized values
        ni_vals = ni.values.filter(categories__isnull=True)
        ni_vals_by_date = {v.date: v for v in ni_vals}

        vals = list(self.values.filter(categories__isnull=True))
        for v in vals:
            nvals: dict[str, float] = {}
            niv = ni_vals_by_date.get(v.date)
            if niv and niv.value:
                val = v.value / niv.value
                val *= cin.unit_multiplier
                v.value /= niv.value
                v.value *= cin.unit_multiplier
                nvals = v.normalized_values or {}
                nvals[str(nci.pk)] = val
            v.normalized_values = nvals
            v.save(update_fields=['normalized_values'])

    def generate_normalized_goals(self, cin: CommonIndicatorNormalizator):
        assert cin.normalizable == self.common
        nci = cin.normalizer

        ni = Indicator.objects.filter(common=nci, organization=self.organization).first()
        if not ni:
            return

        ni_goals_by_date = {g.date: g for g in ni.goals.all()}

        for g in self.goals.all():
            nvals: dict[str, float] = {}
            nig = ni_goals_by_date.get(g.date)
            if nig and nig.value:
                val = g.value / nig.value
                val *= cin.unit_multiplier
                g.value /= nig.value
                g.value *= cin.unit_multiplier
                nvals = g.normalized_values or {}
                nvals[str(nci.pk)] = val
            g.normalized_values = nvals
            g.save(update_fields=['normalized_values'])

    def is_visible_for_user(self, user: UserOrAnon | None):
        """
        Determine if this indicator is visible for a user.

        A None value is interpreted identically to a non-authenticated user.
        """

        if (user is None or not user.is_authenticated) and \
            self.visibility != RestrictedVisibilityModel.VisibilityState.PUBLIC and \
                not cast('PlanQuerySet', self.plans.get_queryset()).visible_for_user(user).exists():
            return False
        return True

    def is_visible_for_public(self) -> bool:
        return self.is_visible_for_user(None)

    @property
    def latest_value_value(self):
        if self.latest_value is None:
            return None
        return self.latest_value.value

    @property
    def latest_value_date(self):
        if self.latest_value is None:
            return None
        return self.latest_value.date

    def __str__(self):
        return self.name_i18n

    @classmethod
    def get_indexed_objects(cls) -> QuerySet[Self]:
        # Return only the actions whose plan supports the current language
        lang = translation.get_language()
        lang_variants = get_available_variants_for_language(lang)
        qs = super().get_indexed_objects()
        q = Q(plans__primary_language__startswith=lang)
        for variant in lang_variants:
            q |= Q(plans__other_languages__contains=[variant])
        qs = qs.filter(q).distinct()
        # FIXME find out how to use action default manager here
        qs = qs.filter(visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        return qs

    def autocomplete_label(self):
        return str(self)


class IndicatorCategoryThrough(models.Model):
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='indicator_category_through')
    category = models.ForeignKey('actions.Category', on_delete=models.CASCADE)

    class Meta:
        db_table = 'indicators_indicator_categories'
        unique_together = ['indicator', 'category']

    def __str__(self):
        return f'{self.indicator}: {self.category}'


@reversion.register()
class Dimension(ClusterableModel):
    """
    A dimension for indicators.

    Dimensions will have several dimension categories.
    """

    name = models.CharField(max_length=100, verbose_name=_('name'))

    public_fields: ClassVar = ['id', 'name', 'categories']

    # type annotations
    categories: RevMany[DimensionCategory]
    plans: RevMany[PlanDimension]

    class Meta:
        verbose_name = _('dimension')
        verbose_name_plural = _('dimensions')

    def __str__(self):
        return self.name

    def delete(self, *args, **kwargs):
        # Check if dimension is used by multiple plans
        if self.plans.count() > 1:
            from django.core.exceptions import ValidationError
            plan_names = [str(pd.plan) for pd in self.plans.all()]
            raise ValidationError(
                _('Cannot delete dimension "%(dimension)s" because it is linked to multiple plans: %(plans)s') % {
                    'dimension': self.name,
                    'plans': ', '.join(plan_names)
                }
            )

        super().delete(*args, **kwargs)


class DimensionCategory(OrderedModel):
    """
    A category in a dimension.

    Indicator values are grouped with this.
    """

    dimension = ParentalKey(Dimension, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100, verbose_name=_('name'))
    default_color = ColorField(
        max_length=50, blank=True, default='', verbose_name=_('default color'),
        help_text=_('Default color for this dimension category in charts'),
    )

    public_fields: ClassVar = ['id', 'dimension', 'name', 'default_color', 'order']

    # type annotations
    values: RevMany[IndicatorValue]

    class Meta:
        verbose_name = _('dimension category')
        verbose_name_plural = _('dimension categories')
        ordering = ['dimension', 'order']

    def __str__(self):
        return self.name

class PlanDimension(models.Model):
    """Mapping of which dimensions a plan is using."""

    dimension = ParentalKey(Dimension, on_delete=models.CASCADE, related_name='plans')
    plan: ParentalKey[Plan] = ParentalKey('actions.Plan', on_delete=models.CASCADE, related_name='dimensions')

    class Meta:
        verbose_name = _('plan dimension')
        verbose_name_plural = _('plan dimensions')
        unique_together = (('plan', 'dimension'),)

    def __str__(self):
        return "%s ∈ %s" % (str(self.dimension), str(self.plan))

class IndicatorDimension(OrderedModel):
    """Mapping of which dimensions an indicator has."""

    dimension: PK[Dimension] = ParentalKey(Dimension, on_delete=models.CASCADE, related_name='instances')
    indicator: PK[Indicator] = ParentalKey(Indicator, on_delete=models.CASCADE, related_name='dimensions')

    public_fields: ClassVar = ['id', 'dimension', 'indicator', 'order']

    class Meta:
        verbose_name = _('indicator dimension')
        verbose_name_plural = _('indicator dimensions')
        ordering = ['indicator', 'order']
        indexes = [
            models.Index(fields=['indicator', 'order']),
        ]
        unique_together = (('indicator', 'dimension'),)

    def __str__(self):
        return "%s ∈ %s" % (str(self.dimension), str(self.indicator))


class CommonIndicatorDimension(OrderedModel):
    """Mapping of which dimensions a common indicator has."""

    dimension = ParentalKey(Dimension, on_delete=models.CASCADE, related_name='common_indicators')
    common_indicator = ParentalKey(CommonIndicator, on_delete=models.CASCADE, related_name='dimensions')

    public_fields: ClassVar = ['id', 'dimension', 'common_indicator', 'order']

    class Meta:
        verbose_name = _('common indicator dimension')
        verbose_name_plural = _('common indicator dimensions')
        ordering = ['common_indicator', 'order']
        indexes = [
            models.Index(fields=['common_indicator', 'order']),
        ]
        unique_together = (('common_indicator', 'dimension'),)

    def __str__(self):
        return "%s ∈ %s" % (str(self.dimension), str(self.common_indicator))

class IndicatorLevelQuerySet(SearchableQuerySetMixin, models.QuerySet['IndicatorLevel']):
    def visible_for_user(self, user: UserOrAnon | None, plan: Plan | str | None = None) -> Self:
        """
        Filter by visibility for a specific user.

        A None value is interpreted identically to a non-authenticated user

        """
        from actions.models import Plan
        if plan:
            if isinstance(plan, str):
                plan = Plan.objects.get(identifier=plan)
            plans = [plan] if plan.is_visible_for_user(user) else []
        else:
            plans = list(Plan.objects.qs.visible_for_user(user))
        if user is None or not user.is_authenticated:
            return self.filter(indicator__visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC,
                               plan__in=plans)
        return self

    def visible_for_public(self) -> Self:
        return self.visible_for_user(None)


if TYPE_CHECKING:
    class IndicatorLevelManager(ModelManager['IndicatorLevel', IndicatorLevelQuerySet]): ...
else:
    IndicatorLevelManager = ModelManager.from_queryset(IndicatorLevelQuerySet)


class IndicatorLevel(ClusterableModel):
    """
    The level for an indicator in an action plan.

    Indicator levels include: operational, tactical and strategic.
    """

    indicator: FK[Indicator] = models.ForeignKey(
        Indicator, related_name='levels', verbose_name=_('indicator'), on_delete=models.CASCADE,
    )
    plan: FK[Plan] = models.ForeignKey(
        'actions.Plan', related_name='indicator_levels', verbose_name=_('plan'), on_delete=models.CASCADE,
    )
    level = models.CharField(max_length=30, verbose_name=_('level'), choices=Indicator.LEVELS)

    public_fields: typing.ClassVar = ['id', 'indicator', 'plan', 'level']

    objects: ClassVar[IndicatorLevelManager] = IndicatorLevelManager()  # pyright: ignore

    class Meta:
        unique_together = (('indicator', 'plan'),)
        verbose_name = _('indicator levels')
        verbose_name_plural = _('indicator levels')

    def __str__(self):
        return "%s in %s (%s)" % (self.indicator, self.plan, self.level)


class IndicatorGraph(models.Model):
    indicator = models.ForeignKey(Indicator, related_name='graphs', on_delete=models.CASCADE)
    data = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    public_fields: ClassVar = ['id', 'indicator', 'data', 'created_at']

    class Meta:
        get_latest_by = 'created_at'

    def __str__(self):
        return "%s (%s)" % (self.indicator, self.created_at)


class IndicatorValue(ClusterableModel):
    """One measurement of an indicator for a certain date/month/year."""

    indicator = ParentalKey(
        Indicator, related_name='values', on_delete=models.CASCADE,
        verbose_name=_('indicator'),
    )
    categories = models.ManyToManyField(
        DimensionCategory, related_name='values', blank=True, verbose_name=_('categories'),
    )
    value = models.FloatField(verbose_name=_('value'))
    date = models.DateField(verbose_name=_('date'))

    # Cached here for performance reasons
    normalized_values: models.JSONField[dict[str, float]] = models.JSONField(null=True, blank=True)

    public_fields: ClassVar = ['id', 'indicator', 'categories', 'value', 'date']

    class Meta:
        verbose_name = _('indicator value')
        verbose_name_plural = _('indicator values')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'

    def clean(self):
        super().clean()
        # FIXME: Check for duplicates on categories

    def __str__(self):
        indicator = self.indicator
        if isinstance(self.date, datetime.date):
            date_str = self.date.isoformat()
        else:
            date_str = self.date

        return f"{indicator} {date_str} {self.value}"


@reversion.register()
class IndicatorGoal(models.Model):
    """The numeric goal which the organization has set for an indicator."""

    indicator = models.ForeignKey(
        Indicator, related_name='goals', on_delete=models.CASCADE,
        verbose_name=_('indicator'),
    )
    value = models.FloatField()
    date = models.DateField(verbose_name=_('date'))

    # Cached here for performance reasons
    normalized_values: models.JSONField[dict[str, float] | None] = models.JSONField(null=True, blank=True)

    public_fields: ClassVar = ['id', 'indicator', 'value', 'date']

    class Meta:
        verbose_name = _('indicator goal')
        verbose_name_plural = _('indicator goals')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'
        unique_together = (('indicator', 'date'),)

    def __str__(self):
        indicator = self.indicator
        date = self.date.isoformat()

        return f"{indicator} {date} {self.value}"


class RelatedIndicator(IndicatorRelationship):
    """A causal relationship between two indicators."""

    HIGH_CONFIDENCE = 'high'
    MEDIUM_CONFIDENCE = 'medium'
    LOW_CONFIDENCE = 'low'
    CONFIDENCE_LEVELS = (
        (HIGH_CONFIDENCE, _('high')),
        (MEDIUM_CONFIDENCE, _('medium')),
        (LOW_CONFIDENCE, _('low')),
    )

    causal_indicator = ParentalKey(
        Indicator, related_name='related_effects', on_delete=models.CASCADE,
        verbose_name=_('causal indicator'),
    )
    effect_indicator = ParentalKey(
        Indicator, related_name='related_causes', on_delete=models.CASCADE,
        verbose_name=_('effect indicator'),
    )
    confidence_level = models.CharField(
        max_length=20, choices=CONFIDENCE_LEVELS,
        verbose_name=_('confidence level'), help_text=_('How confident we are that the causal effect is present'),
    )

    public_fields: ClassVar = ['id', 'effect_type', 'causal_indicator', 'effect_indicator', 'confidence_level']

    class Meta:
        unique_together = (('causal_indicator', 'effect_indicator'),)
        verbose_name = _('related indicator')
        verbose_name_plural = _('related indicators')

    def __str__(self):
        return "%s %s %s" % (self.causal_indicator, self.effect_type, self.effect_indicator)

class ActionIndicatorQuerySet(models.QuerySet['ActionIndicator']):
    def visible_for_user(self, user: UserOrAnon | None) -> Self:
        """
        Filter by visibility for a specific user.

        A None value is interpreted identically to a non-authenticated user
        """
        if user is None or not user.is_authenticated:
            return self.filter(indicator__visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC)
        return self

    def visible_for_public(self) -> Self:
        return self.visible_for_user(None)

    def order_by_setting(self, plan: Plan):
        indicator_ordering = plan.features.indicator_ordering
        if indicator_ordering == OrderBy.NAME:
            lang = plan.primary_language
            collator = utils.get_collator(lang)

            return self.order_by(
                Collate("indicator__name", collator),
            )

        return self


if TYPE_CHECKING:
    class ActionIndicatorManager(ModelManager['ActionIndicator', ActionIndicatorQuerySet]): ...
else:
    ActionIndicatorManager = ModelManager.from_queryset(ActionIndicatorQuerySet)


@reversion.register(follow=['indicator'])
class ActionIndicator(models.Model):
    """Link between an action and an indicator."""

    action: ParentalKey[Action, Action] = ParentalKey(
        'actions.Action', related_name='related_indicators', on_delete=models.CASCADE,
        verbose_name=_('action'),
    )
    indicator: ParentalKey[Indicator, Indicator] = ParentalKey(
        Indicator, related_name='related_actions', on_delete=models.CASCADE,
        verbose_name=_('indicator'),
    )
    effect_type = models.CharField(
        max_length=40, choices=[(val, name) for val, name in IndicatorRelationship.EFFECT_TYPES if val != 'part_of'],
        verbose_name=_('effect type'), help_text=_('What type of effect should the action cause?'),
    )
    indicates_action_progress = models.BooleanField(
        default=False, verbose_name=_('indicates action progress'),
        help_text=_('Set if the indicator should be used to determine action progress'),
    )

    public_fields: ClassVar = ['id', 'action', 'indicator', 'effect_type', 'indicates_action_progress']

    objects: ActionIndicatorManager = ActionIndicatorManager()

    class Meta:
        unique_together = (('action', 'indicator'),)
        verbose_name = _('action indicator')
        verbose_name_plural = _('action indicators')
        ordering = ["indicator"]

    get_effect_type_display: Callable[[], str]

    def __str__(self):
        return "%s ➜ %s ➜ %s" % (self.action, self.get_effect_type_display(), self.indicator)


class IndicatorContactPerson(OrderedModel):
    """Contact person for an indicator."""

    indicator = ParentalKey(
        Indicator, on_delete=models.CASCADE, verbose_name=_('indicator'), related_name='contact_persons',
    )
    person = ParentalKey(
        'people.Person', on_delete=models.CASCADE, verbose_name=_('person'),
    )

    class Meta:
        ordering = ['indicator', 'order']
        indexes = [
            models.Index(fields=['indicator', 'order']),
        ]
        unique_together = (('indicator', 'person'),)
        verbose_name = _('indicator contact person')
        verbose_name_plural = _('indicator contact persons')

    def __str__(self):
        return str(self.person)
