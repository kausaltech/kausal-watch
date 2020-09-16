from django.apps import apps
from django.db import models
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from modeltrans.fields import TranslationField
from modelcluster.models import ClusterableModel
from modelcluster.fields import ParentalKey
import reversion
from wagtail.core.fields import RichTextField

from aplans.utils import IdentifierField, OrderedModel


User = get_user_model()


def latest_plan():
    Plan = apps.get_model('actions', 'Plan')
    if Plan.objects.exists():
        return Plan.objects.latest()
    else:
        return None


class Quantity(ClusterableModel):
    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)

    autocomplete_search_field = 'name'

    class Meta:
        verbose_name = pgettext_lazy('physical', 'quantity')
        verbose_name_plural = pgettext_lazy('physical', 'quantities')
        ordering = ('name',)

    def __str__(self):
        return self.name

    def autocomplete_label(self):
        return str(self)


class Unit(ClusterableModel):
    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)
    short_name = models.CharField(
        max_length=40, null=True, blank=True,
        verbose_name=_('short name')
    )
    verbose_name = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=_('verbose name')
    )
    verbose_name_plural = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=_('verbose name plural')
    )

    autocomplete_search_field = 'name'

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
        null=True, blank=True, verbose_name=_('last retrieved at')
    )
    owner = models.ForeignKey(
        'django_orghierarchy.Organization', null=True, blank=True, verbose_name=_('owner'),
        on_delete=models.SET_NULL,
    )
    owner_name = models.CharField(
        max_length=100, null=True, blank=True, verbose_name=_('owner name'),
        help_text=_('Set if owner organization is not available')
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
    name = models.CharField(max_length=200, verbose_name=_('name'))

    i18n = TranslationField(fields=['name'])

    public_fields = ['id', 'name']

    class Meta:
        verbose_name = _('framework')
        verbose_name_plural = _('frameworks')

    def __str__(self):
        return self.åname


class CommonIndicator(ClusterableModel):
    identifier = IdentifierField()
    name = models.CharField(max_length=200, verbose_name=_('name'))
    description = RichTextField(null=True, blank=True, verbose_name=_('description'))

    quantity = ParentalKey(
        Quantity, related_name='common_indicators', on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'),
    )
    unit = ParentalKey(
        Unit, related_name='common_indicators', on_delete=models.PROTECT,
        verbose_name=_('unit')
    )

    i18n = TranslationField(fields=['name', 'description'])

    public_fields = ['id', 'identifier', 'name', 'description', 'quantity', 'unit']

    class Meta:
        verbose_name = _('common indicator')
        verbose_name_plural = _('common indicators')

    def __str__(self):
        return self.name


class FrameworkIndicator(models.Model):
    identifier = IdentifierField(null=True, blank=True)
    common_indicator = ParentalKey(
        CommonIndicator, related_name='frameworks', on_delete=models.CASCADE,
        verbose_name=_('common indicator')
    )
    framework = ParentalKey(
        Framework, related_name='common_indicators', on_delete=models.CASCADE,
        verbose_name=_('framework')
    )

    public_fields = ['id', 'identifier', 'common_indicator', 'framework']

    class Meta:
        verbose_name = _('framework indicator')
        verbose_name_plural = _('framework indicators')

    def __str__(self):
        return '%s ∈ %s' % (str(self.common_indicator), str(self.framework))


class Indicator(ClusterableModel):
    TIME_RESOLUTIONS = (
        ('year', _('year')),
        ('month', _('month')),
        ('week', _('week')),
        ('day', _('day'))
    )
    LEVELS = (
        ('strategic', _('strategic')),
        ('tactical', _('tactical')),
        ('operational', _('operational')),
    )

    common = models.ForeignKey(
        CommonIndicator, null=True, blank=True, related_name='instances',
        on_delete=models.PROTECT, verbose_name=_('common indicator')
    )
    organization = models.ForeignKey(
        'django_orghierarchy.Organization', related_name='indicators', null=True, blank=True,
        on_delete=models.PROTECT, verbose_name=_('organization'),
    )
    plans = models.ManyToManyField(
        'actions.Plan', through='indicators.IndicatorLevel', blank=True,
        verbose_name=_('plans'), related_name='indicators',
    )
    identifier = IdentifierField(null=True, blank=True)
    name = models.CharField(max_length=200, verbose_name=_('name'))
    quantity = ParentalKey(
        Quantity, related_name='indicators', on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'), null=True, blank=True
    )
    unit = ParentalKey(
        Unit, related_name='indicators', on_delete=models.PROTECT,
        verbose_name=_('unit')
    )
    description = RichTextField(null=True, blank=True, verbose_name=_('description'))
    categories = models.ManyToManyField('actions.Category', blank=True)
    time_resolution = models.CharField(
        max_length=50, choices=TIME_RESOLUTIONS, default=TIME_RESOLUTIONS[0][0],
        verbose_name=_('time resolution')
    )
    latest_graph = models.ForeignKey(
        'IndicatorGraph', null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False
    )
    latest_value = models.ForeignKey(
        'IndicatorValue', null=True, blank=True, related_name='+',
        on_delete=models.SET_NULL, editable=False
    )
    datasets = models.ManyToManyField(
        Dataset, blank=True, verbose_name=_('datasets')
    )

    # summaries = models.JSONField(null=True)
    # E.g.:
    # {
    #    "day_when_target_reached": "2079-01-22",
    #    "yearly_ghg_emission_reductions_left": "1963000",
    # }

    updated_at = models.DateTimeField(
        auto_now=True, editable=False, verbose_name=_('updated at')
    )
    created_at = models.DateTimeField(
        auto_now_add=True, editable=False, verbose_name=_('created at')
    )

    contact_persons_unordered = models.ManyToManyField(
        'people.Person', through='IndicatorContactPerson', blank=True,
        related_name='contact_for_indicators', verbose_name=_('contact persons')
    )

    public_fields = [
        'id', 'common', 'organization', 'identifier', 'name', 'quantity', 'unit', 'description',
        'categories', 'time_resolution', 'latest_value', 'latest_graph', 'datasets', 'updated_at', 'created_at',
        'values', 'plans', 'goals', 'latest_value', 'related_actions', 'actions', 'related_causes',
        'related_effects', 'dimensions',
    ]

    class Meta:
        verbose_name = _('indicator')
        verbose_name_plural = _('indicators')
        ordering = ('-updated_at',)

    def get_latest_graph(self):
        return self.graphs.latest()

    def get_level_for_plan(self, plan):
        level = self.levels.filter(plan=plan).first()
        return level.level if level is not None else None

    def set_latest_value(self):
        try:
            latest_value = self.values.latest()
        except IndicatorValue.DoesNotExist:
            latest_value = None
        if self.latest_value == latest_value:
            return
        self.latest_value = latest_value
        self.save(update_fields=['latest_value'])

    def has_current_data(self):
        return self.latest_value_id is not None

    def has_current_goals(self):
        now = timezone.now()
        return self.goals.filter(date__gte=now).exists()

    def has_datasets(self):
        return self.datasets.exists()
    has_datasets.short_description = _('Has datasets')
    has_datasets.boolean = True

    def has_data(self):
        return self.latest_value_id is not None
    has_data.short_description = _('Has data')
    has_data.boolean = True

    def has_graph(self):
        return self.latest_graph_id is not None
    has_graph.short_description = _('Has a graph')
    has_graph.boolean = True

    def __str__(self):
        return self.name


@reversion.register()
class Dimension(ClusterableModel):
    name = models.CharField(max_length=100, verbose_name=_('name'))

    public_fields = ['id', 'name', 'categories']

    class Meta:
        verbose_name = _('dimension')
        verbose_name_plural = _('dimensions')

    def __str__(self):
        return self.name


class DimensionCategory(OrderedModel):
    dimension = ParentalKey(Dimension, on_delete=models.CASCADE, related_name='categories')
    name = models.CharField(max_length=100, verbose_name=_('name'))

    public_fields = ['id', 'dimension', 'name', 'order']

    class Meta:
        verbose_name = _('dimension category')
        verbose_name_plural = _('dimension categories')
        ordering = ['dimension', 'order']

    def __str__(self):
        return self.name


class IndicatorDimension(OrderedModel):
    dimension = ParentalKey(Dimension, on_delete=models.CASCADE, related_name='instances')
    indicator = ParentalKey(Indicator, on_delete=models.CASCADE, related_name='dimensions')

    public_fields = ['id', 'dimension', 'indicator', 'order']

    class Meta:
        verbose_name = _('indicator dimension')
        verbose_name_plural = _('indicator dimensions')
        ordering = ['indicator', 'order']
        index_together = (('indicator', 'order'),)
        unique_together = (('indicator', 'dimension'),)

    def __str__(self):
        return "%s ∈ %s" % (str(self.dimension), str(self.indicator))


class IndicatorLevel(ClusterableModel):
    indicator = models.ForeignKey(
        Indicator, related_name='levels', verbose_name=_('indicator'), on_delete=models.CASCADE
    )
    plan = models.ForeignKey(
        'actions.Plan', related_name='indicator_levels', verbose_name=_('plan'), on_delete=models.CASCADE,
    )
    level = models.CharField(max_length=30, verbose_name=_('level'), choices=Indicator.LEVELS)

    class Meta:
        unique_together = (('indicator', 'plan'),)
        verbose_name = _('indicator levels')
        verbose_name_plural = _('indicator levels')

    def __str__(self):
        return "%s in %s (%s)" % (self.indicator, self.plan, self.level)


class IndicatorGraph(models.Model):
    indicator = models.ForeignKey(Indicator, related_name='graphs', on_delete=models.CASCADE)
    data = JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        get_latest_by = 'created_at'

    def __str__(self):
        return "%s (%s)" % (self.indicator, self.created_at)


class IndicatorValue(ClusterableModel):
    indicator = ParentalKey(
        Indicator, related_name='values', on_delete=models.CASCADE,
        verbose_name=_('indicator')
    )
    categories = models.ManyToManyField(
        DimensionCategory, related_name='values', blank=True, verbose_name=_('categories')
    )
    value = models.FloatField(verbose_name=_('value'))
    date = models.DateField(verbose_name=_('date'))

    public_fields = ['id', 'indicator', 'categories', 'value', 'date']

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
        date = self.date.isoformat()

        return f"{indicator} {date} {self.value}"


class IndicatorGoal(models.Model):
    plan = models.ForeignKey(
        'actions.Plan', related_name='indicator_goals', on_delete=models.CASCADE,
        verbose_name=_('plan')
    )
    indicator = models.ForeignKey(
        Indicator, related_name='goals', on_delete=models.CASCADE,
        verbose_name=_('indicator')
    )
    scenario = models.ForeignKey(
        'actions.Scenario', related_name='indicator_goals', blank=True, null=True,
        on_delete=models.CASCADE, verbose_name=_('scenario'),
    )
    value = models.FloatField()
    date = models.DateField(verbose_name=_('date'))

    public_fields = ['id', 'plan', 'indicator', 'scenario', 'value', 'date']

    class Meta:
        verbose_name = _('indicator goal')
        verbose_name_plural = _('indicator goals')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'
        unique_together = (('indicator', 'plan', 'scenario', 'date'),)

    def __str__(self):
        indicator = self.indicator
        date = self.date.isoformat()
        if self.scenario is not None:
            scenario_str = ' [%s]' % self.scenario.identifier
        else:
            scenario_str = ''

        return f"{indicator}{scenario_str} {date} {self.value}"


class RelatedIndicator(models.Model):
    INCREASES = 'increases'
    DECREASES = 'decreases'
    PART_OF = 'part_of'

    EFFECT_TYPES = (
        (INCREASES, _('increases')),
        (DECREASES, _('decreases')),
        (PART_OF, _('is a part of')),
    )

    HIGH_CONFIDENCE = 'high'
    MEDIUM_CONFIDENCE = 'medium'
    LOW_CONFIDENCE = 'low'
    CONFIDENCE_LEVELS = (
        (HIGH_CONFIDENCE, _('high')),
        (MEDIUM_CONFIDENCE, _('medium')),
        (LOW_CONFIDENCE, _('low'))
    )

    causal_indicator = models.ForeignKey(
        Indicator, related_name='related_effects', on_delete=models.CASCADE,
        verbose_name=_('causal indicator')
    )
    effect_indicator = models.ForeignKey(
        Indicator, related_name='related_causes', on_delete=models.CASCADE,
        verbose_name=_('effect indicator')
    )
    effect_type = models.CharField(
        max_length=40, choices=EFFECT_TYPES,
        verbose_name=_('effect type'), help_text=_('What type of causal effect is there between the indicators'))
    confidence_level = models.CharField(
        max_length=20, choices=CONFIDENCE_LEVELS,
        verbose_name=_('confidence level'), help_text=_('How confident we are that the causal effect is present')
    )

    class Meta:
        unique_together = (('causal_indicator', 'effect_indicator'),)
        verbose_name = _('related indicator')
        verbose_name_plural = _('related indicators')

    def __str__(self):
        return "%s %s %s" % (self.causal_indicator, self.effect_type, self.effect_indicator)


class ActionIndicator(models.Model):
    action = models.ForeignKey(
        'actions.Action', related_name='related_indicators', on_delete=models.CASCADE,
        verbose_name=_('action')
    )
    indicator = models.ForeignKey(
        Indicator, related_name='related_actions', on_delete=models.CASCADE,
        verbose_name=_('indicator')
    )
    effect_type = models.CharField(
        max_length=40, choices=[(val, name) for val, name in RelatedIndicator.EFFECT_TYPES if val != 'part_of'],
        verbose_name=_('effect type'), help_text=_('What type of effect should the action cause?')
    )
    indicates_action_progress = models.BooleanField(
        default=False, verbose_name=_('indicates action progress'),
        help_text=_('Set if the indicator should be used to determine action progress')
    )

    class Meta:
        unique_together = (('action', 'indicator'),)
        verbose_name = _('action indicator')
        verbose_name_plural = _('action indicators')

    def __str__(self):
        return "%s ➜ %s ➜ %s" % (self.action, self.get_effect_type_display(), self.indicator)


class IndicatorContactPerson(OrderedModel):
    indicator = ParentalKey(
        Indicator, on_delete=models.CASCADE, verbose_name=_('indicator'), related_name='contact_persons'
    )
    person = ParentalKey(
        'people.Person', on_delete=models.CASCADE, verbose_name=_('person'),
    )

    class Meta:
        ordering = ['indicator', 'order']
        index_together = (('indicator', 'order'),)
        unique_together = (('indicator', 'person',),)
        verbose_name = _('indicator contact person')
        verbose_name_plural = _('indicator contact persons')

    def __str__(self):
        return str(self.person)
