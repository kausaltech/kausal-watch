from django.db import models
from django.utils.translation import gettext_lazy as _
from django.contrib.auth import get_user_model


User = get_user_model()


class Unit(models.Model):
    name = models.CharField(max_length=40, verbose_name=_('name'), unique=True)
    verbose_name = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=_('verbose name')
    )

    def __str__(self):
        return self.name


class Indicator(models.Model):
    TIME_RESOLUTIONS = (
        ('year', _('year')),
    )
    plan = models.ForeignKey('actions.Plan', related_name='indicators', on_delete=models.CASCADE)
    name = models.CharField(max_length=100, verbose_name=_('name'))
    unit = models.ForeignKey(
        Unit, related_name='indicators', on_delete=models.CASCADE,
        verbose_name=_('unit')
    )
    description = models.TextField(null=True, blank=True, verbose_name=_('description'))
    categories = models.ManyToManyField('actions.Category', blank=True)
    time_resolution = models.CharField(
        max_length=50, choices=TIME_RESOLUTIONS, default=TIME_RESOLUTIONS[0][0],
        verbose_name=_('time resolution')
    )

    def __str__(self):
        return self.name


class IndicatorEstimate(models.Model):
    indicator = models.ForeignKey(
        Indicator, related_name='estimates', on_delete=models.CASCADE,
        verbose_name=_('indicator')
    )
    result = models.FloatField()
    begins_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)
    scenario = models.ForeignKey(
        'actions.Scenario', related_name='estimates', on_delete=models.CASCADE,
        verbose_name=_('scenario')
    )
    rationale = models.TextField(null=True, blank=True)

    updated_at = models.DateTimeField(auto_now=True, editable=False)
    updated_by = models.ForeignKey(
        User, editable=False, related_name='estimates', on_delete=models.SET_NULL,
        null=True, blank=True,
    )

    def __str__(self):
        indicator = self.indicator.name
        result = self.result
        begins_at = self.begins_at
        scenario = str(self.scenario)

        return f"{indicator}: {result} ({begins_at} {scenario})"
