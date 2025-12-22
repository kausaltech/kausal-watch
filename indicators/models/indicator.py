from __future__ import annotations

import typing
import uuid
from datetime import date
from typing import TYPE_CHECKING, Any, ClassVar, Self, cast

import reversion
from django.contrib.admin import display
from django.contrib.contenttypes.fields import GenericRelation
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.db.models import OneToOneField, Q, QuerySet
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext_lazy as _, pgettext_lazy
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel
from modeltrans.fields import TranslationField
from modeltrans.manager import MultilingualQuerySet
from wagtail.blocks import TextBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.search import index
from wagtail.search.queryset import SearchableQuerySetMixin

from dateutil.relativedelta import relativedelta

from kausal_common.models.types import MLModelManager, ModelManager, OneToOne

from aplans.utils import (
    AdminSaveContext,
    IdentifierField,
    IndirectPlanRelatedModel,
    ModificationTracking,
    RestrictedVisibilityModel,
    get_available_variants_for_language,
    validate_json,
)

from indicators.models.common_indicator import CommonIndicatorNormalizator
from indicators.models.import_log import IndicatorValuesImportLog
from indicators.models.values import IndicatorValue
from orgs.models import Organization
from search.backends import TranslatedAutocompleteField, TranslatedSearchField

if typing.TYPE_CHECKING:
    from wagtail.blocks.stream_block import StreamValue

    from kausal_common.models.types import FK, M2M, RevMany
    from kausal_common.users import UserOrAnon

    from aplans.schema_context import WatchGraphQLContext
    from aplans.types import WatchRequest

    from actions.models import Action
    from actions.models.category import Category, CategoryType
    from actions.models.plan import Plan, PlanQuerySet
    from indicators.models.action_links import ActionIndicator
    from indicators.models.contact_persons import IndicatorContactPerson
    from indicators.models.dimensions import IndicatorDimension
    from indicators.models.metadata import Dataset, Unit
    from indicators.models.relationships import RelatedIndicator
    from indicators.models.values import IndicatorGoal
    from paths_integration._generated_.graphql_client.node_values import NodeValuesNodeMetricDim
    from people.models import Person


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


class IndicatorNonQuantifiedGoalTarget(models.TextChoices):
    INCREASE = 'increase', _('Increase')
    DECREASE = 'decrease', _('Decrease')


@reversion.register(follow=('goals',))
class Indicator(
    ClusterableModel, index.Indexed, ModificationTracking, RestrictedVisibilityModel, IndirectPlanRelatedModel, RevisionMixin
):
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
        'indicators.CommonIndicator',
        null=True,
        blank=True,
        related_name='indicators',
        on_delete=models.PROTECT,
        verbose_name=_('common indicator'),
    )
    organization = ParentalKey(
        'orgs.Organization',
        related_name='indicators',
        on_delete=models.CASCADE,
        verbose_name=_('organization'),
    )
    plans: M2M[Plan, IndicatorLevel] = models.ManyToManyField(
        'actions.Plan',
        through='indicators.IndicatorLevel',
        blank=True,
        verbose_name=_('plans'),
        related_name='indicators',
    )
    identifier = IdentifierField[str | None](null=True, blank=True, max_length=70)
    name = models.CharField(max_length=200, verbose_name=_('name'))
    quantity = ParentalKey(
        'indicators.Quantity',
        related_name='indicators',
        on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'),
        null=True,
        blank=True,
    )
    unit: ParentalKey[Unit] = ParentalKey(
        'indicators.Unit',
        related_name='indicators',
        on_delete=models.PROTECT,
        verbose_name=_('unit'),
    )
    min_value = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_('minimum value'),
        help_text=_('Used in visualizations as the Y axis minimum'),
    )
    max_value = models.FloatField(
        null=True,
        blank=True,
        verbose_name=_('maximum value'),
        help_text=_('Used in visualizations as the Y axis maximum'),
    )
    description = RichTextField[str | None, str | None](null=True, blank=True, verbose_name=_('description'))
    visualizations: StreamField[StreamValue | None] = StreamField(
        [
            ('raw_visualization', TextBlock(validators=(validate_json,)))
        ],
        null=True,
        blank=True,
        verbose_name=_('visualizations'),
    )

    sort_key = models.CharField(
        verbose_name=_('sort key'),
        max_length=200,
        help_text=_('If set, this will be used as the primary criterion for sorting indicators.'),
        blank=True,
        null=True,
    )

    categories: M2M[Category, Any] = ParentalManyToManyField(
        'actions.Category',
        blank=True,
        related_name='indicators',
        through='indicators.IndicatorCategoryThrough',
    )
    time_resolution = models.CharField(
        max_length=50,
        choices=TIME_RESOLUTIONS,
        default=TIME_RESOLUTIONS[0][0],
        verbose_name=_('time resolution'),
    )
    updated_values_due_at = models.DateField(null=True, blank=True, verbose_name=_('updated values due at'))
    latest_graph = models.ForeignKey(
        'indicators.IndicatorGraph',
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
        editable=False,
    )
    latest_value = models.ForeignKey(
        'indicators.IndicatorValue',
        null=True,
        blank=True,
        related_name='+',
        on_delete=models.SET_NULL,
        editable=False,
    )
    reference_value: OneToOne[IndicatorValue | None] = OneToOneField(
        'indicators.IndicatorValue',
        null=True,
        blank=True,
        related_name='reference_for_indicator',
        verbose_name=_('reference value'),
        on_delete=models.SET_NULL,
    )
    datasets: M2M[Dataset, Any] = models.ManyToManyField(
        'indicators.Dataset',
        blank=True,
        verbose_name=_('datasets'),
    )

    # summaries = models.JSONField(null=True)
    # E.g.:
    # {
    #    "day_when_target_reached": "2079-01-22",
    #    "yearly_ghg_emission_reductions_left": "1963000",
    # }

    contact_persons_unordered: M2M[Person, Any] = models.ManyToManyField(
        'people.Person',
        through='indicators.IndicatorContactPerson',
        blank=True,
        related_name='contact_for_indicators',
        verbose_name=_('contact persons'),
    )
    contact_persons: RevMany[IndicatorContactPerson]

    internal_notes = models.TextField(
        blank=True,
        null=True,
        verbose_name=_('internal notes'),
    )

    reference = RichTextField[str | None, str | None](
        blank=True,
        null=True,
        verbose_name=_('reference'),
        max_length=4000,
        help_text=_('What is the reference or source for this indicator?'),
        features=['link'],
    )

    show_trendline = models.BooleanField(
        default=True,
        verbose_name=_('show trend line'),
        help_text=_("Automatically create a trend line for the indicator's total value"),
    )

    desired_trend = models.CharField(
        blank=True,
        null=False,
        verbose_name=_('desired trend'),
        max_length=20,
        default='',
        choices=(
            ('increasing', _('increasing')),
            ('decreasing', _('decreasing')),
            ('', _('attempt to detect automatically')),
        ),
        help_text=_(
            "Which trend in the numerical values of this indicator's goals indicates improvement: when the values are "
            'increasing or decreasing?',
        ),
    )

    show_total_line = models.BooleanField(
        default=True,
        verbose_name=_('show total line'),
        help_text=_('Data categories can be summed to form total for the indicator (draw stacked chart as default)'),
    )

    ticks_count = models.PositiveIntegerField(blank=True, null=True, help_text=_('Number of steps on the y-axis'))
    ticks_rounding = models.PositiveIntegerField(
        blank=True, null=True, help_text=_('Number of significant digits on y-axis ticks')
    )
    value_rounding = models.PositiveIntegerField(
        blank=True, null=True, help_text=_('Number of significant digits when displaying indicator values')
    )
    data_categories_are_stackable = models.BooleanField(
        default=False,
        help_text=_('Data categories can be summed to form a total for the indicator (draw a stacked chart as default)'),
    )

    non_quantified_goal = models.CharField(
        choices=IndicatorNonQuantifiedGoalTarget.choices, null=True, blank=True, verbose_name=_('non-quantified goal')
    )
    non_quantified_goal_date = models.DateField(null=True, blank=True, verbose_name=_('non-quantified goal date'))
    goal_description = models.TextField(null=True, blank=True, verbose_name=_('goal description'))

    # We are anticipating that this will actually be a UUID although currently it is not
    kausal_paths_node_uuid = models.CharField(
        max_length=200,
        editable=True,
        unique=True,
        blank=True,
        null=True,
        verbose_name=_('Node identifier'),  # TODO: change to Node UUID once it's actually a UUID
        help_text=_('The node identifier of the node in Paths where this indicator\'s data is imported from.'),
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
        'id',
        'uuid',
        'common',
        'organization',
        'identifier',
        'name',
        'quantity',
        'unit',
        'description',
        'non_quantified_goal',
        'non_quantified_goal_date',
        'min_value',
        'max_value',
        'categories',
        'time_resolution',
        'latest_value',
        'latest_graph',
        'datasets',
        'updated_at',
        'created_at',
        'values',
        'plans',
        'goals',
        'goal_description',
        'related_actions',
        'actions',
        'related_causes',
        'related_effects',
        'dimensions',
        'reference',
        'show_trendline',
        'desired_trend',
        'show_total_line',
        'ticks_count',
        'ticks_rounding',
        'value_rounding',
        'data_categories_are_stackable',
        'reference_value',
        'sort_key',
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
            plan_qs
            |
            # For unconnected indicators, allow seeing and
            # connecting them for plan admins for plans
            # with same organization as indicator organization
            Plan.objects.filter(organization=self.organization)
        )

    def get_persisted_plans(self):
        from actions.models.plan import Plan
        return Plan.objects.filter(indicator_levels__indicator=self)

    def get_level_for_plan(self, plan):
        level = self.levels.filter(plan=plan).first()
        return level.level if level is not None else None

    def initialize_plan_defaults(self, plan):
        self.organization = plan.organization

    def handle_values_update(self):
        from indicators.models.values import IndicatorValue

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

    def get_notification_context(self, plan, request=None):
        edit_values_url = reverse('indicators_indicator_modeladmin_edit_values', kwargs=dict(instance_pk=self.id))
        return {
            'id': self.id,
            'name': self.name,
            'edit_values_url': edit_values_url,
            'updated_at': self.updated_at,
            'updated_values_due_at': self.updated_values_due_at,
            'view_url': self.get_view_url(plan, request=request),
        }

    def get_view_url(
        self,
        plan: Plan | None = None,
        client_url: str | None = None,
        request: WatchRequest | WatchGraphQLContext | None = None,
    ) -> str:
        if plan is None:
            plan = self.plans.first()
        assert plan is not None
        plan_url = plan.get_view_url(client_url=client_url, active_locale=translation.get_language(), request=request)
        return '%s/indicators/%s' % (plan_url, self.id)

    def clean(self):
        if self.updated_values_due_at:
            if self.time_resolution != 'year':
                raise ValidationError(
                    {'updated_values_due_at': _('Deadlines for value updates are currently only possible for yearly indicators')}
                )
            if self.latest_value is not None and self.updated_values_due_at <= self.latest_value.date + relativedelta(years=1):
                raise ValidationError(
                    {'updated_values_due_at': _('There is already an indicator value for the year preceding the deadline')}
                )

        if self.common:
            if self.common.quantity != self.quantity:
                raise ValidationError(
                    {
                        'quantity': _(
                            'Quantity must be the same as in common indicator (%s)'  # noqa: INT003
                            % self.common.quantity
                        )
                    }
                )
            if self.common.unit != self.unit:
                raise ValidationError(
                    {
                        'unit': _(
                            'Unit must be the same as in common indicator (%s)'  # noqa: INT003
                            % self.common.unit
                        )
                    }
                )
            # Unfortunately it seems we need to check whether dimensions are equal in the form

    def set_categories(self, ctype: CategoryType | str, categories: list[int | Category], plan: Plan | None = None):
        if plan is None:
            plan = self.plans.first()
        assert plan, 'No default plan found.'
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
        from indicators.models.contact_persons import IndicatorContactPerson

        existing_persons = {p.person for p in self.contact_persons.all()}
        new_persons = {d['person'] for d in data}
        IndicatorContactPerson.objects.filter(
            indicator=self,
            person__in=(existing_persons - new_persons),
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

        if (
            (user is None or not user.is_authenticated)
            and self.visibility != RestrictedVisibilityModel.VisibilityState.PUBLIC
            and not cast('PlanQuerySet', self.plans.get_queryset()).visible_for_user(user).exists()
        ):
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

    @transaction.atomic
    def set_values_from_import(
        self,
        metric_dim: NodeValuesNodeMetricDim,
        import_parameters: dict[str, str],
        max_year: int | None = None
    ):
        if len(metric_dim.dimensions) > 0:
            raise NotImplementedError('Only dimensionless nodes supported at the moment')
        if len(metric_dim.years) != len(metric_dim.values):
            raise ValueError('Years and values do not match')

        values_to_remove = IndicatorValue.objects.filter(
            indicator=self
        ).exclude(
            date__year__in=metric_dim.years
        ).exclude(
            date__year__gt=max_year
        )
        values_to_remove.delete()

        for year, value in zip(metric_dim.years, metric_dim.values, strict=True):
            if max_year and year > max_year:
                break
            IndicatorValue.objects.update_or_create(
                indicator=self,
                date__year=year,
                defaults={
                    'value': value,
                    'date': date(year=year, month=12, day=31)
                }
            )
        IndicatorValuesImportLog.objects.create(
            indicator=self,
            source_system=IndicatorValuesImportLog.SOURCE_SYSTEM_KAUSAL_PATHS,
            source_url=import_parameters['source_url'],
            import_parameters=import_parameters,
        )

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
    indicator = models.ForeignKey(
        'indicators.Indicator',
        on_delete=models.CASCADE,
        related_name='indicator_category_through',
    )
    category = models.ForeignKey(
        'actions.Category',
        on_delete=models.CASCADE,
        related_name='indicator_category_through',
    )

    class Meta:
        db_table = 'indicators_indicator_categories'
        unique_together = ['indicator', 'category']

    def __str__(self):
        return f'{self.indicator}: {self.category}'


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
            return self.filter(indicator__visibility=RestrictedVisibilityModel.VisibilityState.PUBLIC, plan__in=plans)
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
        'indicators.Indicator',
        related_name='levels',
        verbose_name=_('indicator'),
        on_delete=models.CASCADE,
    )
    plan: FK[Plan] = models.ForeignKey(
        'actions.Plan',
        related_name='indicator_levels',
        verbose_name=_('plan'),
        on_delete=models.CASCADE,
    )
    level = models.CharField(max_length=30, verbose_name=_('level'), choices=Indicator.LEVELS)

    public_fields: typing.ClassVar = ['id', 'indicator', 'plan', 'level']

    objects: ClassVar[IndicatorLevelManager] = IndicatorLevelManager()

    class Meta:
        unique_together = (('indicator', 'plan'),)
        verbose_name = _('indicator levels')
        verbose_name_plural = _('indicator levels')

    def __str__(self):
        return '%s in %s (%s)' % (self.indicator, self.plan, self.level)
