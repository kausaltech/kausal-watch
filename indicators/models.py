from django.apps import apps
from django.db import models
from django.utils.translation import pgettext_lazy, gettext_lazy as _
from django.utils import timezone
from django.contrib.auth import get_user_model
from django.contrib.postgres.fields import JSONField
from parler.models import TranslatableModel, TranslatedFields

from aplans.utils import IdentifierField, OrderedModel


User = get_user_model()


def latest_plan():
    Plan = apps.get_model('actions', 'Plan')
    if Plan.objects.exists():
        return Plan.objects.latest()
    else:
        return None


class Quantity(TranslatableModel):
    units = models.ManyToManyField('Unit', blank=True, verbose_name=_('units'))

    translations = TranslatedFields(
        name=models.CharField(max_length=40, verbose_name=_('name'))
    )

    class Meta:
        verbose_name = pgettext_lazy('physical', 'quantity')
        verbose_name_plural = pgettext_lazy('physical', 'quantities')
        ordering = ('id',)

    def __str__(self):
        return self.name


class Unit(models.Model):
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

    class Meta:
        verbose_name = _('unit')
        verbose_name_plural = _('units')
        ordering = ('name',)

    def __str__(self):
        return self.name


class DatasetLicense(models.Model):
    name = models.CharField(max_length=50, verbose_name=_('name'), unique=True)

    class Meta:
        verbose_name = _('dataset license')
        verbose_name_plural = _('dataset licenses')

    def __str__(self):
        return self.name


class Dataset(models.Model):
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


class CommonIndicator(TranslatableModel):
    identifier = IdentifierField()
    translations = TranslatedFields(
        name=models.CharField(max_length=100, verbose_name=_('name')),
        description=models.TextField(null=True, blank=True, verbose_name=_('description')),
    )
    quantity = models.ForeignKey(
        Quantity, related_name='common_indicators', on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'), null=True, blank=True
    )

    def __str__(self):
        return self.name


class Indicator(models.Model):
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

    common_indicator = models.ForeignKey(
        CommonIndicator, null=True, blank=True, on_delete=models.SET_NULL,
        related_name='indicators',
    )

    org = models.ForeignKey(
        'django_orghierarchy.Organization', on_delete=models.CASCADE, verbose_name=_('organization'),
        related_name='indicators', null=True, blank=True,
    )
    plans = models.ManyToManyField(
        'actions.Plan', through='indicators.IndicatorLevel', blank=True,
        verbose_name=_('plans')
    )
    identifier = IdentifierField(null=True, blank=True)
    name = models.CharField(max_length=100, verbose_name=_('name'), null=True, blank=True)
    quantity = models.ForeignKey(
        Quantity, related_name='indicators', on_delete=models.PROTECT,
        verbose_name=pgettext_lazy('physical', 'quantity'), null=True, blank=True
    )
    unit = models.ForeignKey(
        Unit, related_name='indicators', on_delete=models.PROTECT,
        verbose_name=_('unit')
    )
    description = models.TextField(null=True, blank=True, verbose_name=_('description'))
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

    class Meta:
        verbose_name = _('indicator')
        verbose_name_plural = _('indicators')
        ordering = ('-updated_at',)

    def get_latest_graph(self):
        return self.graphs.latest()

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


class Dimension(TranslatableModel):
    translations = TranslatedFields(
        name=models.CharField(max_length=100)
    )

    class Meta:
        verbose_name = _('dimension')
        verbose_name_plural = _('dimensions')
        ordering = ('id',)

    def __str__(self):
        return self.name


class DimensionCategory(OrderedModel, TranslatableModel):
    dimension = models.ForeignKey(Dimension, on_delete=models.CASCADE)
    translations = TranslatedFields(
        name=models.CharField(max_length=100)
    )

    class Meta:
        verbose_name = _('dimension category')
        verbose_name_plural = _('dimension categories')
        ordering = ['dimension', 'order']

    def __str__(self):
        return self.name


class IndicatorDimension(OrderedModel):
    dimension = models.ForeignKey(Dimension, on_delete=models.CASCADE, related_name='indicators')
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name='dimensions')

    class Meta:
        verbose_name = _('indicator dimension')
        verbose_name_plural = _('indicator dimensions')
        ordering = ['indicator', 'order']
        unique_together = (('indicator', 'dimension'),)


class IndicatorLevel(models.Model):
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


class IndicatorValue(models.Model):
    indicator = models.ForeignKey(
        Indicator, related_name='values', on_delete=models.CASCADE,
        verbose_name=_('indicator')
    )
    value = models.FloatField(verbose_name=_('value'))
    date = models.DateField(verbose_name=_('date'))
    dimension_categories = models.ManyToManyField(DimensionCategory, blank=True,)

    class Meta:
        verbose_name = _('indicator value')
        verbose_name_plural = _('indicator values')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'
        unique_together = (('indicator', 'date'),)

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
    value = models.FloatField()
    date = models.DateField(verbose_name=_('date'))

    class Meta:
        verbose_name = _('indicator goal')
        verbose_name_plural = _('indicator goals')
        ordering = ('indicator', 'date')
        get_latest_by = 'date'
        unique_together = (('indicator', 'plan', 'date'),)

    def __str__(self):
        indicator = self.indicator
        date = self.date.isoformat()

        return f"{indicator} {date} {self.value}"


class IndicatorEstimate(models.Model):
    indicator = models.ForeignKey(
        Indicator, related_name='estimates', on_delete=models.CASCADE,
        verbose_name=_('indicator')
    )
    result_low = models.FloatField(verbose_name=_('low estimate'))
    result_high = models.FloatField(verbose_name=_('high estimate'), null=True, blank=True)
    begins_at = models.DateField(verbose_name=_('begins at'))
    ends_at = models.DateField(verbose_name=_('ends at'), null=True, blank=True)
    forecast = models.BooleanField(
        verbose_name=_('measured'), default=False,
        help_text=_('Is this estimate based on forecast or measurement?')
    )
    scenario = models.ForeignKey(
        'actions.Scenario', related_name='estimates', on_delete=models.CASCADE,
        verbose_name=_('scenario')
    )
    rationale = models.TextField(null=True, blank=True, verbose_name=_('rationale'))

    updated_at = models.DateTimeField(auto_now=True, editable=False)
    updated_by = models.ForeignKey(
        User, editable=False, related_name='estimates', on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    class Meta:
        verbose_name = _('indicator estimate')
        verbose_name_plural = _('indicator estimates')

    def __str__(self):
        indicator = self.indicator.name
        result = str(self.result_low)
        if self.result_high is not None:
            result = "%s–%s" % (self.result_low, self.result_high)
        begins_at = self.begins_at
        scenario = str(self.scenario)

        return f"{indicator}: {result} ({begins_at} {scenario})"


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
        max_length=40, choices=RelatedIndicator.EFFECT_TYPES,
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
    indicator = models.ForeignKey(
        Indicator, on_delete=models.CASCADE, verbose_name=_('indicator'), related_name='contact_persons'
    )
    person = models.ForeignKey(
        'people.Person', on_delete=models.CASCADE, verbose_name=_('person')
    )

    class Meta:
        ordering = ['indicator', 'order']
        index_together = (('indicator', 'order'),)
        unique_together = (('indicator', 'person',),)
        verbose_name = _('indicator contact person')
        verbose_name_plural = _('indicator contact persons')

    def __str__(self):
        return str(self.person)
