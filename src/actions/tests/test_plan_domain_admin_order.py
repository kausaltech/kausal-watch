import pytest

from actions.models import Plan
from actions.models.plan import PlanDomain
from actions.tests.factories import PlanDomainFactory
from actions.wagtail_admin import PlanAdmin

pytestmark = pytest.mark.django_db


def _domains_formset_class(rf, superuser, plan):
    from aplans.context_vars import ctx_instance, ctx_request

    request = rf.get('/')
    request.user = superuser
    with ctx_request.activate(request), ctx_instance.activate(plan):
        form_class = PlanAdmin().get_edit_handler().bind_to_model(Plan).get_form_class()
    return form_class.formsets['domains']


def _formset_data(domains_in_order):
    data = {
        'domains-TOTAL_FORMS': str(len(domains_in_order)),
        'domains-INITIAL_FORMS': str(len(domains_in_order)),
        'domains-MIN_NUM_FORMS': '0',
        'domains-MAX_NUM_FORMS': '1000',
    }
    for i, domain in enumerate(domains_in_order):
        data |= {
            f'domains-{i}-id': str(domain.pk),
            f'domains-{i}-hostname': domain.hostname,
            f'domains-{i}-deployment_environment': domain.deployment_environment,
            f'domains-{i}-ORDER': str(i + 1),
        }
    return data


def test_reordering_domains_in_the_plan_form_persists_the_order(rf, superuser, plan):
    first = PlanDomainFactory.create(plan=plan, hostname='first.city.gov', deployment_environment='production')
    second = PlanDomainFactory.create(plan=plan, hostname='second.city.gov', deployment_environment='production')
    formset_class = _domains_formset_class(rf, superuser, plan)

    formset = formset_class(_formset_data([second, first]), instance=plan, prefix='domains')
    assert formset.is_valid(), formset.errors
    formset.save()

    hostnames = list(PlanDomain.objects.filter(plan=plan).values_list('hostname', flat=True))
    assert hostnames == ['second.city.gov', 'first.city.gov']
    plan.refresh_from_db()
    assert plan.get_view_url() == 'https://second.city.gov'


def test_domains_panel_explains_which_domain_is_used(rf, superuser, plan):
    from aplans.context_vars import ctx_instance, ctx_request

    request = rf.get('/')
    request.user = superuser
    with ctx_request.activate(request), ctx_instance.activate(plan):
        handler = PlanAdmin().get_edit_handler()

    def find(panel):
        if getattr(panel, 'relation_name', None) == 'domains':
            return panel
        for child in getattr(panel, 'children', []):
            found = find(child)
            if found is not None:
                return found
        return None

    panel = find(handler)
    assert panel is not None
    assert 'first domain in this list' in str(panel.help_text)
