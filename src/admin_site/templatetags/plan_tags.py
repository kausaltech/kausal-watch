from __future__ import annotations

from django import template

from actions.models.plan import Plan

register = template.Library()


@register.filter
def is_scheduled(plan: Plan) -> bool:
    return plan.publication_state == Plan.PublicationState.SCHEDULED
