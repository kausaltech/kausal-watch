from __future__ import annotations

import re

from django.core.management import CommandError, call_command
from django.utils import translation

import pytest

from actions.models.plan import Plan
from actions.tests.factories import PlanFactory
from copying.main import copy_plan

pytestmark = pytest.mark.django_db


@pytest.fixture
def translated_plan(plan_with_pages: Plan) -> Plan:
    """Return a plan in English and Finnish whose name and version name are translated into Finnish."""
    assert plan_with_pages.primary_language == 'en'
    assert plan_with_pages.other_languages == ['fi']
    # Not `save()`: its side effects would run before pytest-factoryboy creates the plan's general content.
    Plan.objects.filter(pk=plan_with_pages.pk).update(
        name='Climate plan',
        version_name='Current',
        i18n={'name_fi': 'Ilmasto-ohjelma', 'version_name_fi': 'Voimassa oleva'},
    )
    plan_with_pages.refresh_from_db()
    return plan_with_pages


def _copy(plan: Plan, **kwargs) -> Plan:
    plan_copy = copy_plan(plan, new_plan_identifier='plan-copy', **kwargs)
    plan_copy.refresh_from_db()
    return plan_copy


def test_copy_gets_the_given_translations(translated_plan):
    plan_copy = _copy(
        translated_plan,
        new_plan_name='Draft plan',
        new_plan_name_translations={'fi': 'Luonnosohjelma'},
        version_name='Draft',
        version_name_translations={'fi': 'Luonnos'},
    )
    assert plan_copy.name == 'Draft plan'
    assert plan_copy.version_name == 'Draft'
    assert plan_copy.i18n == {'name_fi': 'Luonnosohjelma', 'version_name_fi': 'Luonnos'}
    translated_plan.refresh_from_db()
    assert translated_plan.i18n == {'name_fi': 'Ilmasto-ohjelma', 'version_name_fi': 'Voimassa oleva'}


def test_empty_translation_falls_back_to_the_primary_language(translated_plan):
    plan_copy = _copy(translated_plan, new_plan_name='Draft plan', version_name='Draft', version_name_translations={'fi': ''})
    assert plan_copy.i18n == {}
    with translation.override('fi'):
        assert plan_copy.name_i18n == 'Draft plan'
        assert plan_copy.version_name_i18n == 'Draft'


def test_default_name_is_translated_like_the_original(translated_plan):
    expected_name = translated_plan.default_name_for_copying()
    expected_name_fi = translated_plan.default_name_for_copying('fi')
    assert 'Ilmasto-ohjelma' in expected_name_fi
    plan_copy = _copy(translated_plan)
    assert plan_copy.name == expected_name
    assert plan_copy.i18n['name_fi'] == expected_name_fi


def test_copy_keeps_the_version_name_unless_one_is_given(translated_plan):
    plan_copy = _copy(translated_plan, new_plan_name='Draft plan')
    assert plan_copy.version_name == 'Current'
    assert plan_copy.i18n == {'version_name_fi': 'Voimassa oleva'}


def test_empty_version_name_removes_it_with_its_translations(translated_plan):
    plan_copy = _copy(translated_plan, new_plan_name='Draft plan', version_name='')
    assert plan_copy.version_name == ''
    assert 'version_name_fi' not in plan_copy.i18n


def test_version_name_translations_require_a_version_name(translated_plan):
    with pytest.raises(ValueError, match='without a version name'):
        copy_plan(translated_plan, version_name_translations={'fi': 'Luonnos'})


def test_translations_into_other_languages_are_rejected(translated_plan):
    with pytest.raises(ValueError, match='does not have'):
        copy_plan(translated_plan, new_plan_name='Draft plan', new_plan_name_translations={'sv': 'Utkast'})


def test_default_name_without_a_translation_is_empty(translated_plan):
    translated_plan.i18n = {}
    assert translated_plan.default_name_for_copying('fi') == ''


def test_default_name_translation_has_the_same_copy_number(translated_plan):
    PlanFactory.create(name=translated_plan.default_name_for_copying())
    name = translated_plan.default_name_for_copying()
    name_fi = translated_plan.default_name_for_copying('fi')
    assert re.search(r'\b2\b', name)
    assert re.search(r'\b2\b', name_fi)


def test_command_passes_translations(translated_plan):
    call_command(
        'copy_plan',
        translated_plan.identifier,
        '--dest-identifier=plan-copy',
        '--dest-name=Draft plan',
        '--dest-name-translation=fi=Luonnosohjelma',
        '--version-name=Draft',
        '--version-name-translation=fi=Luonnos',
    )
    plan_copy = Plan.objects.get(identifier='plan-copy')
    assert plan_copy.i18n == {'name_fi': 'Luonnosohjelma', 'version_name_fi': 'Luonnos'}


@pytest.mark.parametrize(
    'args',
    [
        ['--version-name-translation=fi=Luonnos'],
        ['--dest-name-translation=Luonnosohjelma'],
    ],
)
def test_command_rejects_malformed_translations(translated_plan, args):
    with pytest.raises(CommandError):
        call_command('copy_plan', translated_plan.identifier, '--dest-identifier=plan-copy', *args)
