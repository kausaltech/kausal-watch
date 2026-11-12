import logging
from datetime import timedelta

from django.db.models import Q

logger = logging.getLogger(__name__)


def determine_basic_info(action):
    if not action.contact_persons.exists():
        return False
    if not action.description.strip():
        return False
    if not action.tasks.exists():
        return False
    return True


def determine_future_task(action):
    now = action.plan.now_in_local_timezone()
    year_from_now = now + timedelta(days=365)
    # A continuous task without a due date is ongoing work, which counts as planned
    if not action.tasks.active().filter(Q(due_at__lte=year_from_now) | Q(due_at__isnull=True)).exists():
        return False
    return True


def determine_indicator(action):
    ais = action.related_indicators.filter(indicates_action_progress=True).select_related('indicator')
    for ai in ais:
        ind = ai.indicator
        if ind.has_current_goals() and ind.has_current_data():
            return True
    return False


POINT_MAP = {
    'basic_info': determine_basic_info,
    'future_task': determine_future_task,
    'indicator': determine_indicator,
}


def determine_monitoring_quality(action, points):
    new_points = set()
    for point in points:
        determine_func = POINT_MAP.get(point.identifier)
        if not determine_func:
            logger.error("Do not know how to determine monitoring quality for '%s'" % point.identifier)
            continue
        if determine_func(action):
            new_points.add(point.id)

    existing_points = {p.id for p in action.monitoring_quality_points.all()}
    if new_points != existing_points:
        action.monitoring_quality_points.set(new_points)
