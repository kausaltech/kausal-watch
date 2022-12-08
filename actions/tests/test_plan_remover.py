import pytest

pytestmark = pytest.mark.django_db

#  NOP  actions.models.plan.Plan -> actions.models.plan.Plan
#  NOP  actions.models.plan.Plan -> actions.models.category.CommonCategoryType

#  CAS! actions.models.plan.Plan -> wagtail.core.models.sites.Site

#  CAS  actions.models.plan.Plan -> actions.models.category.CategoryType
#  CAS? actions.models.plan.Plan -> django.contrib.auth.models.Group
#  CAS? actions.models.plan.Plan -> images.models.AplansImage
#  CAS? actions.models.plan.Plan -> orgs.models.Organization
#  CAS? actions.models.plan.Plan -> wagtail.core.models.collections.Collection

#  CAS! actions.models.action.Action                    -> actions.models.plan.Plan
#  CAS! actions.models.action.ActionDecisionLevel       -> actions.models.plan.Plan
#  CAS! actions.models.action.ActionImpact              -> actions.models.plan.Plan
#  CAS! actions.models.action.ActionImplementationPhase -> actions.models.plan.Plan
#  CAS! actions.models.action.ActionSchedule            -> actions.models.plan.Plan
#  CAS! actions.models.action.ActionStatus              -> actions.models.plan.Plan
#  CAS! actions.models.category.CategoryType            -> actions.models.plan.Plan
#  CAS! actions.models.features.PlanFeatures            -> actions.models.plan.Plan

# +CAS? actions.models.plan.GeneralPlanAdmin            -> actions.models.plan.Plan
# +CAS? admin.site.models.ClientPlan                    -> actions.models.plan.Plan

#  CAS! actions.models.plan.ImpactGroup                 -> actions.models.plan.Plan
#  CAS! actions.models.plan.MonitoringQualityPoint      -> actions.models.plan.Plan
#  CAS! actions.models.plan.PlanDomain                  -> actions.models.plan.Plan
#  CAS! actions.models.plan.Scenario                    -> actions.models.plan.Plan
#  CAS! actions.models.report.ReportType                -> actions.models.plan.Plan
#  CAS! content.models.SiteGeneralContent               -> actions.models.plan.Plan
#  CAS! indicators.models.IndicatorLevel                -> actions.models.plan.Plan
#  CAS! indicators.models.PlanCommonIndicator           -> actions.models.plan.Plan
#  CAS! notifications.models.BaseTemplate               -> actions.models.plan.Plan
#  CAS! orgs.models.OrganizationPlanAdmin               -> actions.models.plan.Plan
#  CAS! pages.models.PlanLink                           -> actions.models.plan.Plan
#  OK   users.models.User                               -> actions.models.plan.Plan
#  CAS! feedback.models.UserFeedback                    -> actions.models.plan.Plan backup!


@pytest.fixture
def plan_with_actions_factory(plan_factory, action_factory):
    def plan_with_actions():
        plan = plan_factory()
        for i in range(0, 10):
            action_factory(plan=plan)
        return plan
    return plan_with_actions


def test_active_people_intact(plan_with_actions_factory, person_factory):
    plan1 = plan_with_actions_factory()
    plan2 = plan_with_actions_factory()
    common_people = [person_factory() for p in range(0, 10)]
    people1 = [person_factory() for p in range(0, 10)]
    people2 = [person_factory() for p in range(0, 10)]
    # translated root pages
    # site, pages in general

    print(plan1)
    assert False
