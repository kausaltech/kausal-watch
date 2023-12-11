from __future__ import annotations
from functools import cached_property

from actions.models import ActionStatus, ActionImplementationPhase, Plan
from reports.models import Report


class PlanSpecificCache:
    plan: 'Plan'

    def __init__(self, plan: 'Plan'):
        self.plan = plan

    @cached_property
    def action_statuses(self) -> list[ActionStatus]:
        return list(self.plan.action_statuses.all())

    @cached_property
    def implementation_phases(self) -> list[ActionImplementationPhase]:
        return list(self.plan.action_implementation_phases.all())

    def get_action_status(self, *, id: int | None = None, identifier: str | None = None) -> ActionStatus | None:
        # Must supply either id or identifier
        assert bool(id is None) != bool(identifier is None)

        for a_s in self.action_statuses:
            if id is not None:
                if a_s.id == id:
                    return a_s
            else:
                if a_s.identifier == identifier:
                    return a_s
        return None

    @cached_property
    def latest_reports(self) -> list[Report]:
        qs = (
            Report.objects
                .filter(type__plan=self.plan)
                .order_by('type', '-start_date')
                .distinct('type')
        )
        return list(qs)

    @classmethod
    def fetch(cls, plan_id: int) -> Plan:
        return Plan.objects.get(id=plan_id)


class WatchObjectCache:
    plan_caches: dict[int, PlanSpecificCache]
    admin_plan_cache: PlanSpecificCache | None

    def __init__(self):
        self.plan_caches = {}
        self.admin_plan_cache = None

    def for_plan_id(self, plan_id: int) -> PlanSpecificCache:
        plan_cache = self.plan_caches.get(plan_id)
        if plan_cache is None:
            plan = PlanSpecificCache.fetch(plan_id)
            plan_cache = PlanSpecificCache(plan)
            self.plan_caches[plan_id] = plan_cache
        return plan_cache

    def for_plan(self, plan: Plan) -> PlanSpecificCache:
        return self.for_plan_id(plan.id)
