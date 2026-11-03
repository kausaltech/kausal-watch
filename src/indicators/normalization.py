"""Warnings about indicator data that cannot be normalized, for the people who edit it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.conf import settings
from django.urls import reverse
from django.utils.translation import gettext as _

if TYPE_CHECKING:
    from datetime import date

    from actions.models import Plan
    from indicators.models import Indicator
    from indicators.models.indicator import NormalizationGap
    from users.models import User


@dataclass
class NormalizationWarning:
    message: str
    # Where the normalizer indicator's data can be fixed; None if the user may not edit it or it does not exist
    normalizer_url: str | None
    normalizer_link_text: str | None


def _format_date(indicator: Indicator, d: date) -> str:
    if indicator.time_resolution == 'year':
        return str(d.year)
    if indicator.time_resolution == 'month':
        return f'{d.year}-{d.month:02}'
    return d.isoformat()


def get_indicator_data_edit_url(indicator: Indicator) -> str:
    """Return the admin URL for editing the values of `indicator`, or its edit page if there is no data editor."""
    # The data editor is part of the extensions
    if 'kausal_watch_extensions' in settings.INSTALLED_APPS:
        return reverse('indicators_indicator_edit_values', kwargs=dict(instance_pk=indicator.pk))
    return reverse('wagtailsnippets_indicators_indicator:edit', args=[indicator.pk])


def _make_missing_data_warning(
    indicator: Indicator, gap: NormalizationGap, ni: Indicator, user: User, plan: Plan
) -> NormalizationWarning:
    dates = [_format_date(indicator, d) for d in gap.value_dates]
    dates += [_('%(date)s (goal)') % {'date': _format_date(indicator, d)} for d in gap.goal_dates]
    message = _(
        'This indicator can only partly be normalized by "%(normalizer)s", which has no value (or a value of zero) '
        'for these dates: %(dates)s. Until this is fixed, websites may not offer to show this indicator normalized '
        'by "%(normalizer)s".'
    ) % {'normalizer': ni.name, 'dates': ', '.join(dates)}
    if not user.can_modify_indicator(indicator=ni, plan=plan):
        return NormalizationWarning(message=message, normalizer_url=None, normalizer_link_text=None)
    return NormalizationWarning(
        message=message,
        normalizer_url=get_indicator_data_edit_url(ni),
        normalizer_link_text=_('Edit the data of "%(normalizer)s"') % {'normalizer': ni.name},
    )


def _make_warnings(indicator: Indicator, gap: NormalizationGap, user: User, plan: Plan) -> list[NormalizationWarning]:
    ni = gap.normalizer_indicator
    if ni is None:
        message = _(
            'This indicator is normalized by "%(normalizer)s", but its organization has no indicator for it. Until '
            'there is one, websites may not offer to show this indicator normalized by "%(normalizer)s".'
        ) % {'normalizer': gap.normalizer.name}
        return [NormalizationWarning(message=message, normalizer_url=None, normalizer_link_text=None)]

    warnings = []
    if gap.value_dates or gap.goal_dates:
        warnings.append(_make_missing_data_warning(indicator, gap, ni, user, plan))
    if gap.has_unnormalized_categorized_values:
        # Normalizing them is not implemented, so there is nothing to link to
        message = _(
            'Values for dimension categories cannot be normalized, so websites may not offer to show the graph of '
            'this indicator normalized by "%(normalizer)s".'
        ) % {'normalizer': ni.name}
        warnings.append(NormalizationWarning(message=message, normalizer_url=None, normalizer_link_text=None))
    return warnings


def get_normalization_warnings(indicator: Indicator, user: User, plan: Plan) -> list[NormalizationWarning]:
    """Explain to `user`, who edits `indicator` in `plan`, which of its data cannot be normalized and why."""
    return [warning for gap in indicator.get_normalization_gaps() for warning in _make_warnings(indicator, gap, user, plan)]
