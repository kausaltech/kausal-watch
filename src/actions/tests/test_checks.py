from __future__ import annotations

from django.core.checks import Error
from django.test import override_settings

from actions.checks import check_hostname_plan_domains


@override_settings(HOSTNAME_PLAN_DOMAINS=[])
def test_empty_hostname_plan_domains_produces_error():
    errors = check_hostname_plan_domains(app_configs=None)
    assert len(errors) == 1
    assert isinstance(errors[0], Error)
    assert errors[0].id == 'watch.D001'


@override_settings(HOSTNAME_PLAN_DOMAINS=['localhost'])
def test_only_localhost_produces_error():
    errors = check_hostname_plan_domains(app_configs=None)
    assert len(errors) == 1
    assert isinstance(errors[0], Error)
    assert errors[0].id == 'watch.D002'


@override_settings(HOSTNAME_PLAN_DOMAINS=['example.com'])
def test_valid_domain_produces_no_error():
    errors = check_hostname_plan_domains(app_configs=None)
    assert errors == []


@override_settings(HOSTNAME_PLAN_DOMAINS=['localhost', 'example.com'])
def test_localhost_with_other_domain_produces_no_error():
    errors = check_hostname_plan_domains(app_configs=None)
    assert errors == []
