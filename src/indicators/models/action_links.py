from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self

import reversion
from django.db import models
from django.db.models.functions import Collate
from django.utils.translation import gettext_lazy as _
from modelcluster.fields import ParentalKey

from kausal_common.models.types import ModelManager

from aplans import utils
from aplans.utils import RestrictedVisibilityModel

from indicators.models.relationships import IndicatorRelationship

if TYPE_CHECKING:
    from collections.abc import Callable

    from kausal_common.users import UserOrAnon

    from actions.models import Action
    from actions.models.plan import Plan
    from indicators.models.indicator import Indicator


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
        from actions.models.features import OrderBy

        indicator_ordering = plan.features.indicator_ordering
        if indicator_ordering == OrderBy.NAME:
            lang = plan.primary_language
            collator = utils.get_collator(lang)

            return self.order_by(
                Collate('indicator__name', collator),
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
        'actions.Action',
        related_name='related_indicators',
        on_delete=models.CASCADE,
        verbose_name=_('action'),
    )
    indicator: ParentalKey[Indicator, Indicator] = ParentalKey(
        'indicators.Indicator',
        related_name='related_actions',
        on_delete=models.CASCADE,
        verbose_name=_('indicator'),
    )
    effect_type = models.CharField(
        max_length=40,
        choices=[(val, name) for val, name in IndicatorRelationship.EFFECT_TYPES if val != 'part_of'],
        verbose_name=_('effect type'),
        help_text=_('What type of effect should the action cause?'),
    )
    indicates_action_progress = models.BooleanField(
        default=False,
        verbose_name=_('indicates action progress'),
        help_text=_('Set if the indicator should be used to determine action progress'),
    )

    public_fields: ClassVar = ['id', 'action', 'indicator', 'effect_type', 'indicates_action_progress']

    objects: ActionIndicatorManager = ActionIndicatorManager()

    class Meta:
        unique_together = (('action', 'indicator'),)
        verbose_name = _('action indicator')
        verbose_name_plural = _('action indicators')
        ordering = ['indicator']

    get_effect_type_display: Callable[[], str]

    def __str__(self):
        return '%s ➜ %s ➜ %s' % (self.action, self.get_effect_type_display(), self.indicator)
