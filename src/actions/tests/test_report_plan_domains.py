from io import StringIO

from django.core.management import call_command

import pytest

from actions.models.plan import PlanDomain
from actions.tests.factories import PlanDomainFactory, PlanFactory

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _wildcard(settings):
    settings.HOSTNAME_PLAN_DOMAINS = ['example.com']


def _report(*args: str) -> str:
    out = StringIO()
    call_command('report_plan_domains', *args, stdout=out)
    return out.getvalue()


def _plan_section(report: str, identifier: str) -> str:
    sections = report.split('\n\n')
    return next(s for s in sections if s.startswith(identifier + ' '))


def test_marks_the_domain_in_use_and_flags_competing_production_domains():
    plan = PlanFactory.create(identifier='twodomains')
    PlanDomainFactory.create(plan=plan, hostname='first.city.gov', deployment_environment='production')
    PlanDomainFactory.create(plan=plan, hostname='second.city.gov', deployment_environment='production')

    section = _plan_section(_report(), 'twodomains')

    assert 'https://first.city.gov' in section.splitlines()[0]
    assert '* first.city.gov' in section
    assert '  second.city.gov' in section
    assert '2 production domains compete' in section


def test_a_preview_domain_listed_first_is_shown_but_not_in_use():
    plan = PlanFactory.create(identifier='previewfirst')
    preview = PlanDomainFactory.create(plan=plan, hostname='preview.city.gov', deployment_environment='preview')
    PlanDomainFactory.create(plan=plan, hostname='city.gov', deployment_environment='production')
    PlanDomain.objects.filter(pk=preview.pk).update(order=0)

    section = _plan_section(_report(), 'previewfirst')

    lines = section.splitlines()
    assert 'preview.city.gov' in lines[1]
    assert not lines[1].lstrip().startswith('*')
    assert '* city.gov' in section
    assert 'compete' not in section


def test_plan_without_domains_uses_the_wildcard():
    PlanFactory.create(identifier='nodomains')

    section = _plan_section(_report(), 'nodomains')

    assert 'https://nodomains.example.com' in section
    assert 'wildcard' in section


def test_multiple_only_lists_just_the_plans_with_competing_domains():
    single = PlanFactory.create(identifier='single')
    PlanDomainFactory.create(plan=single, hostname='single.city.gov', deployment_environment='production')
    multi = PlanFactory.create(identifier='multi')
    PlanDomainFactory.create(plan=multi, hostname='a.city.gov', deployment_environment='production')
    PlanDomainFactory.create(plan=multi, hostname='b.city.gov', deployment_environment='production')

    report = _report('--multiple-only')

    assert 'multi ' in report
    assert 'single ' not in report
