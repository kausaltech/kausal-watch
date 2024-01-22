from __future__ import annotations

import datetime
from enum import Enum
from typing import Callable, NotRequired, TypedDict, TYPE_CHECKING

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from aplans.utils import ConstantMetadata, MetadataEnum

if TYPE_CHECKING:
    from actions.models import Action, Plan, ActionStatus
    from aplans.cache import WatchObjectCache

Sentiment = Enum('Sentiment', names='POSITIVE NEGATIVE NEUTRAL')


class SummaryContext(TypedDict, total=False):
    plan: Plan
    plan_id: int
    cache: NotRequired[WatchObjectCache]


class ActionStatusSummary(ConstantMetadata['ActionStatusSummaryIdentifier', SummaryContext]):
    default_label: str
    color: str
    is_completed: bool
    is_active: bool
    sentiment: Sentiment
    label: str

    def __init__(self,
                 default_label=None,
                 color=None,
                 is_completed=False,
                 is_active=False,
                 sentiment=None):
        self.default_label = default_label
        self.color = color
        self.is_completed = is_completed
        self.is_active = is_active
        self.sentiment = sentiment

    def with_context(self, context: SummaryContext):  # type: ignore[override]
        if context is None:
            raise ValueError('Context with plan required to resolve status label')
        if 'plan' not in context and 'plan_id' not in context:
            raise KeyError('Action status values depend on the plan')
        if self.identifier is None:
            raise ValueError('with_identifier must be called before with_context')
        plan = context.get('plan')
        identifier: str = self.identifier.name.lower()
        cache = context.get('cache')
        if cache is not None:
            plan_id = context.get('plan_id')
            if plan_id is None and plan is not None:
                plan_id = plan.id
            status = context['cache'].for_plan_id(plan_id).get_action_status(identifier=identifier)
        else:
            status = plan.action_statuses.filter(plan=plan, identifier=identifier).first()
        if status is not None:
            self.label = status.name_i18n
        else:
            self.label = self.default_label
        return self


class ActionStatusSummaryIdentifier(MetadataEnum):
    # The ordering is significant
    COMPLETED = ActionStatusSummary(
        default_label=_('Completed'),
        color='green090',
        is_completed=True,
        is_active=False,
        sentiment=Sentiment.POSITIVE
    )
    ON_TIME = ActionStatusSummary(
        default_label=_('On time'),
        color='green050',
        is_completed=False,
        is_active=True,
        sentiment=Sentiment.POSITIVE
    )
    IN_PROGRESS = ActionStatusSummary(
        default_label=_('In progress'),
        color='green050',
        is_completed=False,
        is_active=True,
        sentiment=Sentiment.POSITIVE
    )
    NOT_STARTED = ActionStatusSummary(
        default_label=_('Not started'),
        color='green010',
        is_completed=False,
        is_active=True,
        sentiment=Sentiment.NEUTRAL
    )
    LATE = ActionStatusSummary(
        default_label=_('Late'),
        color='yellow050',
        is_completed=False,
        is_active=True,
        sentiment=Sentiment.NEGATIVE
    )
    CANCELLED = ActionStatusSummary(
        default_label=_('Cancelled'),
        color='grey030',
        is_completed=False,
        is_active=False,
        sentiment=Sentiment.NEUTRAL
    )
    OUT_OF_SCOPE = ActionStatusSummary(
        default_label=_('Out of scope'),
        color='grey030',
        is_completed=False,
        is_active=False,
        sentiment=Sentiment.NEUTRAL
    )
    MERGED = ActionStatusSummary(
        default_label=_('Merged'),
        color='grey030',
        is_completed=True,
        is_active=False,
        sentiment=Sentiment.NEUTRAL
    )
    POSTPONED = ActionStatusSummary(
        default_label=_('Postponed'),
        color='blue030',
        is_completed=False,
        is_active=False,
        sentiment=Sentiment.NEUTRAL
    )
    UNDEFINED = ActionStatusSummary(
        default_label=_('Unknown'),
        color='grey010',
        is_completed=False,
        is_active=True,
        sentiment=Sentiment.NEUTRAL
    )

    def get_identifier(self):
        return self.name.lower()

    def __str__(self):
        return f'{self.name}.{str(self.value)}'

    @classmethod
    def for_status(cls, status: 'ActionStatus'):
        if status is None:
            return cls.UNDEFINED
        status_identifier = status.identifier.lower() if status else None
        try:
            return next(s for s in cls if s.name.lower() == status_identifier)
        except StopIteration:
            return cls.UNDEFINED

    @classmethod
    def for_action(cls, action: 'Action'):
        # FIXME: Some plans in production have inconsistent Capitalized identifiers
        # Once the db has been cleaned up, this match logic
        # should be revisited
        status_identifier = action.status.identifier.lower() if action.status else None
        phase = action.implementation_phase.identifier.lower() if action.implementation_phase else None
        if action.merged_with_id is not None:
            return cls.MERGED
        # TODO: check phase "completed" property
        if phase == 'completed':
            return cls.COMPLETED
        # phase: "begun"? "implementation?"
        status_match = cls.for_status(action.status)
        if status_match == cls.UNDEFINED and phase == 'not_started':
            return cls.NOT_STARTED
        return status_match


Comparison = Enum('Comparison', names='LTE GT')


class ActionTimeliness(ConstantMetadata['ActionTimelinessIdentifier', SummaryContext]):
    color: str | None
    sentiment: Sentiment | None
    label: str | None
    boundary: Callable[['Plan'], int]
    comparison: Comparison | None
    identifier: 'ActionTimelinessIdentifier'
    days: int

    def __init__(self,
        boundary: Callable[['Plan'], int],
        color: str | None = None,
        sentiment: Sentiment | None = None,
        label: str | None = None,
        comparison: Comparison | None = None,
    ):
        self.color = color
        self.sentiment = sentiment
        self.label = label
        self.comparison = comparison
        self.boundary = boundary

    def _get_label(self, plan: 'Plan'):
        if self.comparison == Comparison.LTE:
            return _('Under %d days') % self._get_days(plan)
        return _('Over %d days') % self._get_days(plan)

    def _get_days(self, plan: 'Plan'):
        return self.boundary(plan)

    def with_context(self, context: SummaryContext):
        if context is None:
            raise ValueError('Context with plan required to resolve timeliness')
        if 'plan' not in context:
            raise KeyError('Action timeliness values depend on the plan')
        if self.identifier is None:
            raise ValueError('with_identifier must be called before with_context')
        self.days = self._get_days(context['plan'])
        self.label = self._get_label(context['plan'])
        return self


class ActionTimelinessIdentifier(MetadataEnum):
    OPTIMAL = ActionTimeliness(
        color='green070',
        sentiment=Sentiment.POSITIVE,
        boundary=(lambda plan: plan.action_update_target_interval),
        comparison=Comparison.LTE
    )
    ACCEPTABLE = ActionTimeliness(
        color='green030',
        sentiment=Sentiment.NEUTRAL,
        boundary=(lambda plan: plan.action_update_acceptable_interval),
        comparison=Comparison.LTE
    )
    LATE = ActionTimeliness(
        color='yellow050',
        sentiment=Sentiment.NEGATIVE,
        boundary=(lambda plan: plan.action_update_acceptable_interval),
        comparison=Comparison.GT
    )
    STALE = ActionTimeliness(
        color='red050',
        sentiment=Sentiment.NEGATIVE,
        boundary=(lambda plan: plan.get_action_days_until_considered_stale()),
        comparison=Comparison.GT
    )

    @classmethod
    def for_action(cls, action: 'Action'):
        plan = action.plan
        age = timezone.now() - action.updated_at
        if age <= datetime.timedelta(days=cls.OPTIMAL.value.boundary(plan)):
            return cls.OPTIMAL
        if age <= datetime.timedelta(days=cls.ACCEPTABLE.value.boundary(plan)):
            return cls.ACCEPTABLE
        # We do not distinguish between late and stale for now
        return cls.LATE
