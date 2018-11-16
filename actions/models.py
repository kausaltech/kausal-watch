from django.db import models
from django.db.models import Q
from django.utils.translation import gettext_lazy as _

from django_orghierarchy.models import Organization
from ordered_model.models import OrderedModel
from markdownx.models import MarkdownxField


class Plan(models.Model):
    name = models.CharField(max_length=100, verbose_name=_('name'))
    identifier = models.CharField(max_length=50, unique=True, verbose_name=_('identifier'))
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        verbose_name = _('plan')
        verbose_name_plural = _('plans')
        get_latest_by = 'created_at'

    def __str__(self):
        return self.name


def latest_plan():
    if Plan.objects.exists():
        return Plan.objects.latest()
    else:
        return None


class Action(OrderedModel):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, default=latest_plan,
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=200, verbose_name=_('name'))
    official_name = models.CharField(
        max_length=100, null=True, blank=True,
        verbose_name=_('official name'),
        help_text=_('The name as approved by an official party')
    )
    identifier = models.CharField(
        max_length=50, verbose_name=_('identifier'),
        help_text=_('The identifier for this action (e.g. number)')
    )
    description = MarkdownxField(
        null=True, blank=True,
        verbose_name=_('description'),
        help_text=_('What does this action involve in more detail?'))
    impact = models.IntegerField(
        null=True, blank=True,
        verbose_name=_('impact'),
        help_text=_('The impact this action has in measurable quantity (e.g. t CO₂e)')
    )
    schedule = models.ManyToManyField(
        'ActionSchedule', blank=True,
        verbose_name=_('schedule')
    )
    responsible_parties = models.ManyToManyField(
        Organization, through='ActionResponsibleParty', blank=True,
        verbose_name=_('responsible parties')
    )
    categories = models.ManyToManyField(
        'Category', blank=True, verbose_name=_('categories')
    )
    indicators = models.ManyToManyField(
        'indicators.Indicator', blank=True, verbose_name=_('indicators')
    )

    order_with_respect_to = 'plan'

    class Meta:
        verbose_name = _('action')
        verbose_name_plural = _('actions')
        ordering = ('plan', 'order')
        index_together = (('plan', 'order'),)

    def __str__(self):
        return "%s. %s" % (self.identifier, self.name)

    def clean(self):
        # FIXME: Make sure FKs and M2Ms point to objects that are within the
        # same action plan.
        super().clean()


class ActionResponsibleParty(OrderedModel):
    action = models.ForeignKey(Action, on_delete=models.CASCADE)
    org = models.ForeignKey(
        Organization, on_delete=models.CASCADE,
        limit_choices_to=Q(dissolution_date=None)
    )

    order_with_respect_to = 'action'

    class Meta:
        ordering = ['action', 'order']
        index_together = (('action', 'order'),)


class ActionSchedule(OrderedModel):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    name = models.CharField(max_length=100)
    begins_at = models.DateField()
    ends_at = models.DateField(null=True, blank=True)

    order_with_respect_to = 'plan'

    class Meta(OrderedModel.Meta):
        ordering = ('plan', 'order')
        index_together = (('plan', 'order'),)
        verbose_name = _('action schedule')
        verbose_name_plural = _('action schedules')

    def __str__(self):
        return self.name


class CategoryType(models.Model):
    plan = models.ForeignKey(Plan, on_delete=models.CASCADE)
    name = models.CharField(max_length=50)
    identifier = models.CharField(max_length=50)

    class Meta:
        unique_together = (('plan', 'identifier'),)
        ordering = ('plan', 'name')
        verbose_name = _('category type')
        verbose_name_plural = _('category types')

    def __str__(self):
        return "%s (%s)" % (self.name, self.identifier)


class Category(OrderedModel):
    type = models.ForeignKey(CategoryType, on_delete=models.CASCADE)
    parent = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL)
    name = models.CharField(max_length=100)
    identifier = models.CharField(max_length=50)

    order_with_respect_to = 'type'

    class Meta:
        unique_together = (('type', 'identifier'),)
        verbose_name = _('category')
        verbose_name_plural = _('categories')
        ordering = ('type', 'identifier')

    def __str__(self):
        return "%s %s" % (self.identifier, self.name)


class Scenario(models.Model):
    plan = models.ForeignKey(
        Plan, on_delete=models.CASCADE, related_name='plans',
        verbose_name=_('plan')
    )
    name = models.CharField(max_length=100, verbose_name=_('nimi'))
    identifier = models.CharField(max_length=50, verbose_name=_('identifier'))
    description = models.TextField(null=True, blank=True, verbose_name=_('description'))

    class Meta:
        unique_together = (('plan', 'identifier'),)
        verbose_name = _('scenario')
        verbose_name_plural = _('scenarios')

    def __str__(self):
        return self.name
