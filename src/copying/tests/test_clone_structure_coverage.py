from __future__ import annotations

from typing import TYPE_CHECKING

from django.apps import apps
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import ForeignKey, ManyToManyField, ManyToManyRel, ManyToOneRel
from django.test.utils import isolate_apps
from modelcluster.fields import ParentalKey
from wagtail.models import Page

from kausal_common.datasets.models import Dataset, DatasetSchema

from actions.models.action import Action
from actions.models.attributes import AttributeType
from actions.models.category import Category
from actions.models.plan import Plan
from copying.main import (
    ATTRIBUTE_TYPE_CLONE_STRUCTURE,
    CLONE_STRUCTURE_ROOTS,
    DATASET_CLONE_STRUCTURE,
    DATASET_SCHEMA_CLONE_STRUCTURE,
    DIMENSION_CLONE_STRUCTURE,
    GENERIC_REFERENCE_MODELS,
    INDICATOR_CLONE_STRUCTURE,
    MODELS_COPIED_OUTSIDE_CLONE_STRUCTURES,
    PLAN_CLONE_STRUCTURE,
    RELATIONS_OUTSIDE_CLONE_STRUCTURES,
    UNIQUE_FIELD_COPY_POLICIES,
    Excluded,
    _is_excluded_model,
    _iter_clone_structure_models,
    get_unclassified_unique_field_copy_policies,
)
from indicators.models.dimensions import Dimension
from indicators.models.indicator import Indicator

if TYPE_CHECKING:
    from collections.abc import Generator, Iterable

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

    def test_dataset_schema_clone_structure_coverage(self):
        _check_coverage(DatasetSchema, DATASET_SCHEMA_CLONE_STRUCTURE, set())

    def test_dataset_clone_structure_coverage(self):
        _check_coverage(Dataset, DATASET_CLONE_STRUCTURE, set())

    def test_unique_field_copy_policy_coverage(self):
        assert get_unclassified_unique_field_copy_policies() == []

    def test_unique_field_copy_policy_coverage_detects_multi_field_constraints(self, monkeypatch):
        policies = dict(UNIQUE_FIELD_COPY_POLICIES)
        policies[Plan] = {k: v for k, v in policies[Plan].items() if k != 'short_identifier'}
        monkeypatch.setattr('copying.main.UNIQUE_FIELD_COPY_POLICIES', policies)
        assert get_unclassified_unique_field_copy_policies() == [
            'actions.Plan.(short_identifier, organization)',
            'actions.Plan.(short_identifier, parent)',
        ]

    def test_unique_field_copy_policy_coverage_accepts_joining_field_in_constraint(self):
        # `Action` has a unique constraint on `(plan, identifier)` without a policy for either field, but `plan` is the
        # foreign key by which `PLAN_CLONE_STRUCTURE` reaches it
        assert 'identifier' not in UNIQUE_FIELD_COPY_POLICIES[Action]
        assert not any(label.startswith('actions.Action.(') for label in get_unclassified_unique_field_copy_policies())


# Relations and generic references that copying does not handle yet although it should. Each entry is a bug; fix it and
# then classify the entry in `RELATIONS_OUTSIDE_CLONE_STRUCTURES` or `GENERIC_REFERENCE_MODELS` instead.
KNOWN_GAPS: dict[str, str] = {
    'actions.Plan.related_plans': 'The related plans are lost',
    'kausal_watch_extensions.CartographyProviderCredentials.plan': (
        "Map credentials are not copied, so map blocks in the copied pages use the original plan's credentials"
    ),
    'taggit.TaggedItem': 'The tags of copied images and documents are lost',
    'wagtailcore.CollectionViewRestriction.collection': 'View restrictions of the collection are lost',
    'wagtailcore.Revision': (
        'Page copies keep all revisions of the originals, but only the latest one has its references updated, so '
        'reverting to an older revision references objects of the original plan'
    ),
    'wagtailcore.WorkflowPage.page': 'Workflows assigned to pages are lost',
}


def _get_structure_models() -> set[type[Model]]:
    models: set[type[Model]] = set()
    for root_model, structure in CLONE_STRUCTURE_ROOTS:
        models |= set(_iter_clone_structure_models(root_model, structure))
    return models


def _is_copied_page_cluster_child(model_class: type[Model]) -> bool:
    for field in model_class._meta.fields:
        if not isinstance(field, ParentalKey):
            continue
        page_model = field.related_model
        assert isinstance(page_model, type)
        if not issubclass(page_model, Page):
            continue
        accessor_name = field.remote_field.get_accessor_name()
        excluded_fields = {*page_model.default_exclude_fields_in_copy, *page_model.exclude_fields_in_copy}
        if accessor_name not in excluded_fields:
            return True
    return False


def _is_copied_outside_clone_structures(model_class: type[Model]) -> bool:
    if any(issubclass(model_class, m) for m in MODELS_COPIED_OUTSIDE_CLONE_STRUCTURES):
        return True
    return _is_copied_page_cluster_child(model_class)


def _iter_relations_outside_clone_structures() -> Generator[str]:
    """Yield the labels of the relations that must be listed in `RELATIONS_OUTSIDE_CLONE_STRUCTURES`."""
    structure_models = _get_structure_models()
    for model_class in apps.get_models():
        if _is_excluded_model(model_class):
            continue
        if model_class in structure_models or _is_copied_outside_clone_structures(model_class):
            # Copied, so its forward relations are remapped to the copies of their targets
            continue
        for field in model_class._meta.get_fields(include_parents=False):
            if not isinstance(field, (ForeignKey, ManyToManyField)):
                continue
            target = field.related_model
            assert isinstance(target, type)
            # Visible reverse relations of models in the clone structures are covered by `_check_coverage()`
            hidden_from_structure = target in structure_models and field.remote_field.hidden
            if hidden_from_structure or _is_copied_outside_clone_structures(target):
                yield f'{model_class._meta.label}.{field.name}'
    copied_models = [m for m in apps.get_models() if m in structure_models or _is_copied_outside_clone_structures(m)]
    yield from _iter_auto_created_many_to_many_fields(copied_models)


def _iter_auto_created_many_to_many_fields(models: Iterable[type[Model]]) -> Generator[str]:
    """Yield the labels of the many-to-many fields of the given models whose through model is auto-created."""
    for model_class in models:
        for field in model_class._meta.local_many_to_many:
            through = field.remote_field.through
            assert isinstance(through, type)
            if through._meta.auto_created:
                yield f'{model_class._meta.label}.{field.name}'


def _iter_generic_reference_models() -> Generator[str]:
    """Yield the labels of the models that must be listed in `GENERIC_REFERENCE_MODELS`."""
    for model_class in apps.get_models():
        has_generic_foreign_key = any(isinstance(f, GenericForeignKey) for f in model_class._meta.private_fields)
        has_content_type = any(
            isinstance(f, ForeignKey) and f.related_model is ContentType
            for f in model_class._meta.get_fields(include_parents=False)
        )
        if has_generic_foreign_key or has_content_type:
            yield model_class._meta.label


def _is_installed(label: str) -> bool:
    app_label, model_name = label.split('.')[:2]
    try:
        apps.get_model(app_label, model_name)
    except LookupError:
        return False
    return True


def _check_classification(found: set[str], classified: dict[str, str], registry_name: str) -> None:
    unclassified = found - classified.keys() - KNOWN_GAPS.keys()
    assert not unclassified, (
        f'Copying a plan does not account for the following. Make sure copying handles them and add them to '
        f'{registry_name}:\n' + '\n'.join(f'  {label}' for label in sorted(unclassified))
    )
    both = classified.keys() & KNOWN_GAPS.keys()
    assert not both, f'Entries are both in {registry_name} and in KNOWN_GAPS: {sorted(both)}'
    bogus = {label for label in classified.keys() - found if _is_installed(label)}
    assert not bogus, f'Entries in {registry_name} that do not need to be listed: {sorted(bogus)}'


class TestCopyBlindSpots:
    """
    Check for data that relates to copied objects in ways the clone structures cannot express.

    `TestCloneStructureCoverage` only sees reverse relations that the clone structures can follow. These tests find
    the remaining ways data can depend on a copied object, so each must be classified explicitly.
    """

    def test_relations_outside_clone_structures_are_classified(self):
        found = set(_iter_relations_outside_clone_structures())
        _check_classification(found, RELATIONS_OUTSIDE_CLONE_STRUCTURES, 'RELATIONS_OUTSIDE_CLONE_STRUCTURES')

    def test_generic_reference_models_are_classified(self):
        found = set(_iter_generic_reference_models())
        _check_classification(found, GENERIC_REFERENCE_MODELS, 'GENERIC_REFERENCE_MODELS')

    def test_auto_created_many_to_many_fields_of_page_models_are_found(self):
        with isolate_apps('copying'):

            class PageWithManyToMany(Page):
                categories = ManyToManyField(Category)

                class Meta:
                    app_label = 'copying'

        # Page models are copied with `Page.copy()`, which keeps the relation pointing to the original categories
        assert _is_copied_outside_clone_structures(PageWithManyToMany)
        found = set(_iter_auto_created_many_to_many_fields([PageWithManyToMany]))
        assert found == {'copying.PageWithManyToMany.categories'}

    def test_known_gaps_are_not_stale(self):
        found = set(_iter_relations_outside_clone_structures()) | set(_iter_generic_reference_models())
        stale = {label for label in KNOWN_GAPS.keys() - found if _is_installed(label)}
        assert not stale, f'Entries in KNOWN_GAPS that are no longer found, remove them: {sorted(stale)}'
