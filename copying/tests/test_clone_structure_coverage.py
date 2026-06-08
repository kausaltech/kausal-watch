from __future__ import annotations

from typing import TYPE_CHECKING

from django.db.models import ManyToManyRel, ManyToOneRel

from actions.models.attributes import AttributeType
from actions.models.plan import Plan
from copying.main import (
    ATTRIBUTE_TYPE_CLONE_STRUCTURE,
    DIMENSION_CLONE_STRUCTURE,
    INDICATOR_CLONE_STRUCTURE,
    PLAN_CLONE_STRUCTURE,
    Excluded,
    _is_excluded_model,
    get_unclassified_unique_field_copy_policies,
)
from indicators.models.dimensions import Dimension
from indicators.models.indicator import Indicator

if TYPE_CHECKING:
    from django.db.models import Model

    from copying.main import CloneStructure


def _check_coverage(model_class: type[Model], structure: CloneStructure, visited: set[type[Model]]) -> None:
    if model_class in visited:
        return
    visited.add(model_class)

    relation_names = set()
    covered = set(structure.keys())
    missing = []
    for field in model_class._meta.get_fields():
        if not isinstance(field, (ManyToOneRel, ManyToManyRel)):
            continue
        relation_names.add(field.name)
        related = field.related_model
        # The type stubs allow `related_model` to be a string for unresolved
        # lazy relations, but all models are fully initialized by test time.
        assert not isinstance(related, str), (
            f"Unexpected unresolved related model '{related}' on {model_class.__name__}.{field.name}"
        )
        if field.name in covered:
            entry = structure[field.name]
            if not isinstance(entry, Excluded):
                _check_coverage(related, entry, visited)
            continue
        if _is_excluded_model(related):
            continue
        missing.append(f"  '{field.name}' -> {related.__name__}")

    if missing:
        raise AssertionError(
            f'{model_class.__name__} has relations not accounted for in its clone structure.\n'
            'Add them as sub-structures to copy, or mark as EXCLUDED:\n' + '\n'.join(missing)
        )

    bogus = covered - relation_names
    if bogus:
        raise AssertionError(
            f'{model_class.__name__} clone structure contains keys that do not match any relation on the model:\n'
            + '\n'.join(f"  '{name}'" for name in sorted(bogus))
        )


class TestCloneStructureCoverage:
    def test_plan_clone_structure_coverage(self):
        _check_coverage(Plan, PLAN_CLONE_STRUCTURE, set())

    def test_attribute_type_clone_structure_coverage(self):
        _check_coverage(AttributeType, ATTRIBUTE_TYPE_CLONE_STRUCTURE, set())

    def test_indicator_clone_structure_coverage(self):
        _check_coverage(Indicator, INDICATOR_CLONE_STRUCTURE, set())

    def test_dimension_clone_structure_coverage(self):
        _check_coverage(Dimension, DIMENSION_CLONE_STRUCTURE, set())

    def test_unique_field_copy_policy_coverage(self):
        assert get_unclassified_unique_field_copy_policies() == []
