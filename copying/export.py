"""
Single-tenant data export.

Produce a self-contained JSON dump of one plan's data (and nothing belonging to any other
tenant), in Django's standard serialization format -- the same format ``dumpdata`` emits and
``loaddata`` consumes.

Unlike ``destructively_trim_db`` (a denylist: delete every other tenant and hope nothing
leaks), this is an allowlist: it walks only the objects that provably belong to the plan,
reusing the declarative clone structures from ``copying.main`` as the definition of plan
ownership. Because it never visits another tenant's rows, it cannot leak them.

See ``docs/architecture/single-tenant-export.md`` for the design.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.core import serializers
from wagtail.models import Page
from wagtail.models.reference_index import ReferenceIndex

from copying.main import (
    DATASET_SCHEMA_CLONE_STRUCTURE,
    DIMENSION_CLONE_STRUCTURE,
    INDICATOR_CLONE_STRUCTURE,
    MODELS_NOT_COPIED,
    PLAN_CLONE_STRUCTURE,
    Excluded,
    _iter_clone_structure_instances,
    iter_plan_owned_instances,
)
from copying.utils import get_foreign_keys, get_generic_foreign_keys
from documents.models import AplansDocument
from images.models import AplansImage
from indicators.models.dimensions import Dimension
from indicators.models.indicator import Indicator
from orgs.models import Organization
from people.models import Person

if TYPE_CHECKING:
    from collections.abc import Callable, Generator

    from django.db.models import Model
    from wagtail.models import Collection, Site

    from actions.models.plan import Plan
    from copying.main import CloneEntry, CloneStructure


def _deepcopy_structure(structure: CloneStructure) -> CloneStructure:
    """Deep-copy a clone structure, preserving the shared ``EXCLUDED`` sentinel by identity."""
    result: CloneStructure = {}
    for key, entry in structure.items():
        result[key] = entry if isinstance(entry, Excluded) else _deepcopy_structure(entry)
    return result


def _set(structure: CloneStructure, path: list[str], value: CloneEntry) -> None:
    """
    Set the entry at ``path`` (a chain of relation names) in ``structure``.

    Every parent on the path must already exist and be a (non-excluded) sub-structure, so
    typos and reclassifications of relations that copy doesn't know about fail loudly.
    """
    *parents, last = path
    node = structure
    for key in parents:
        entry = node[key]
        if isinstance(entry, Excluded):
            raise TypeError(f'Cannot descend into excluded relation {key!r} on path {path!r}')
        node = entry
    if last not in node:
        raise ValueError(f'Relation {last!r} is not a key of the clone structure at path {path!r}')
    node[last] = value


# Relations that copy drops purely to avoid remapping references to the copied objects. An
# export preserves primary keys verbatim, so these are safe -- and wanted -- to include.
def build_export_plan_structure(
    *,
    include_pledges: bool = False,
    include_feedback: bool = False,
    include_audit_logs: bool = False,
) -> CloneStructure:
    """
    Build the plan traversal structure for an export.

    Starts from ``PLAN_CLONE_STRUCTURE`` (so relations newly added on the copy side flow
    through automatically) and applies the export-specific reclassifications documented in
    ``docs/architecture/single-tenant-export.md``. Deliberately dropped relations (other
    plans, plan domains, legacy and our-side-only data) are left ``EXCLUDED`` as in copy.
    """
    structure = _deepcopy_structure(PLAN_CLONE_STRUCTURE)

    # --- Re-include plan-owned content that copy drops only to avoid reference remapping ---
    # Reports embed action snapshots that reference original PKs; a remapping problem for
    # copy, but not for a PK-preserving export.
    _set(structure, ['report_types', 'reports'], {'action_snapshots': {}})
    # Plan links are cluster children; copy leaves them out (its own TODO), but they are plan content.
    _set(structure, ['links'], {})
    # Change-log history (each of these is a leaf model with no further relations to traverse).
    for changelog_rel in (
        'actionchangelogmessage_set',
        'indicatorchangelogmessage_set',
        'categorychangelogmessage_set',
        'pagechangelogmessage_set',
    ):
        _set(structure, [changelog_rel], {})

    # --- Privacy-gated content (off by default) ---
    if include_pledges:
        # Citizen commitments to pledges.
        _set(structure, ['pledges', 'commitments'], {})
    if include_feedback:
        # Citizen-submitted feedback and staff notification preferences.
        _set(structure, ['user_feedbacks'], {})
        _set(structure, ['pledges', 'user_feedbacks'], {})
        _set(structure, ['actions', 'contact_persons', 'notification_preferences'], {})
        _set(structure, ['general_admins_ordered', 'notification_preferences'], {})
    if include_audit_logs:
        _set(structure, ['planscopedmodellogentry'], {})
        _set(structure, ['planscopedpagelogentry'], {})

    return structure


# The default export structure (conservative privacy defaults). Exposed for tests and docs.
EXPORT_PLAN_STRUCTURE: CloneStructure = build_export_plan_structure()


def _iter_page_and_specific(page: Page) -> Generator[Model]:
    """
    Yield both rows that make up a Wagtail page.

    Pages use multi-table inheritance, so each page is stored as a base ``wagtailcore.page``
    row plus a concrete-subclass row. ``loaddata`` needs both.
    """
    yield page
    specific = page.specific
    if type(specific) is not Page:
        yield specific


def iter_plan_page_instances(plan: Plan) -> Generator[Model]:
    """
    Yield every page owned by the plan, base and concrete rows for each.

    Covers the plan site's root page and every documentation root page, each together with
    its translations (separate per-locale page trees) and all their descendants. The clone
    structures deliberately skip pages because copy delegates them to Wagtail's ``Page.copy``.
    """
    roots: list[Page] = []
    site: Site | None = plan.site
    if site is not None:
        # A Wagtail Site always has a (non-nullable) root page.
        root = site.root_page
        roots.append(root)
        roots.extend(root.get_translations(inclusive=False))
    for doc_root in plan.documentation_root_pages.all():
        roots.append(doc_root)
        roots.extend(doc_root.get_translations(inclusive=False))

    for root in roots:
        for page in root.get_descendants(inclusive=True):
            yield from _iter_page_and_specific(page)


def iter_plan_collection_instances(plan: Plan) -> Generator[Model]:
    """Yield the plan's root collection and its descendant collections."""
    root_collection: Collection | None = plan.root_collection
    if root_collection is None:
        return
    yield from root_collection.get_descendants(inclusive=True)


def iter_plan_media_instances(plan: Plan) -> Generator[Model]:
    """
    Yield the image and document rows living in the plan's collections.

    Only the database rows are exported; the binary files live in object storage and are
    handled out of band (see the ``--media-manifest`` option of the ``export_plan`` command).
    """
    root_collection: Collection | None = plan.root_collection
    if root_collection is None:
        return
    collections = root_collection.get_descendants(inclusive=True)
    yield from AplansImage.objects.filter(collection__in=collections)
    yield from AplansDocument.objects.filter(collection__in=collections)


def _iter_relational_reference_targets(instance: Model) -> Generator[Model]:
    """Yield every object an instance points at via a forward FK, generic FK or M2M."""
    for fk in get_foreign_keys(instance):
        target = getattr(instance, fk.name, None)
        if target is not None:
            yield target
    for gfk in get_generic_foreign_keys(instance):
        target = getattr(instance, gfk.name, None)
        if target is not None:
            yield target
    for field in instance._meta.many_to_many:
        yield from getattr(instance, field.name).all()


def _iter_org_ancestors(
    organizations: list[Organization],
    seen: set[tuple[type[Model], object]],
) -> Generator[Organization]:
    """Yield the not-yet-seen ancestors of the given organizations, transitively."""
    # Index-based loop over a list that grows as ancestors are appended, so ancestors of
    # ancestors are covered too.
    index = 0
    while index < len(organizations):
        organization = organizations[index]
        index += 1
        for ancestor in organization.get_ancestors():
            key = (Organization, ancestor.pk)
            if key in seen:
                continue
            seen.add(key)
            organizations.append(ancestor)
            yield ancestor


def iter_referenced_shared_objects(instances: list[Model]) -> Generator[Model]:
    """
    Yield the shared/global objects referenced by the collected instances.

    A one-level pull of the ``MODELS_NOT_COPIED`` targets (organizations, persons, users,
    common indicators, ...) referenced by a foreign key, generic foreign key or M2M on a
    collected instance. Their own relations are *not* followed -- that is what would drag
    another tenant's data in -- with one deliberate exception: ``Organization`` ancestors are
    followed transitively so the org hierarchy is not truncated to just the referenced nodes.

    Off by default; enabled to make the dump interpretable on its own (names, not bare PKs).
    """
    shared_models = set(MODELS_NOT_COPIED)
    seen: set[tuple[type[Model], object]] = set()
    organizations: list[Organization] = []

    for instance in instances:
        for target in _iter_relational_reference_targets(instance):
            key = (type(target), target.pk)
            if type(target) not in shared_models or key in seen:
                continue
            seen.add(key)
            if isinstance(target, Organization):
                organizations.append(target)
            yield target

    yield from _iter_org_ancestors(organizations, seen)


def collect_export_instances(
    plan: Plan,
    *,
    structure: CloneStructure = EXPORT_PLAN_STRUCTURE,
    include_indicators: bool = True,
    include_referenced_shared_objects: bool = False,
) -> list[Model]:
    """
    Collect every instance belonging to ``plan``, deduplicated by ``(type, pk)``.

    Combines the relation-tree traversal (via ``iter_plan_owned_instances``) with the Wagtail
    site, collection, page and media rows the clone structures don't reach, then closes over
    two kinds of dangling reference so the dump is internally consistent:

    - indicators referenced by exported rows but not in ``plan.indicators`` (see
      ``_add_referenced_indicators``);
    - images/documents referenced by exported content but living outside the plan's
      collections (see ``_add_referenced_media``).

    When ``include_referenced_shared_objects`` is set, also appends the shared objects from
    ``iter_referenced_shared_objects``.
    """
    seen: set[tuple[type[Model], object]] = set()
    instances: list[Model] = []

    def add(candidates: Generator[Model] | list[Model]) -> list[Model]:
        added: list[Model] = []
        for instance in candidates:
            key = (type(instance), instance.pk)
            if key in seen:
                continue
            seen.add(key)
            instances.append(instance)
            added.append(instance)
        return added

    add(iter_plan_owned_instances(plan, plan_structure=structure, include_indicators=include_indicators))
    if plan.site is not None:
        add([plan.site])
    add(iter_plan_collection_instances(plan))
    add(iter_plan_page_instances(plan))
    add(iter_plan_media_instances(plan))
    if include_indicators:
        _add_referenced_indicator_graph(plan, instances, add, seen)
    _add_referenced_media(instances, add)
    if include_referenced_shared_objects:
        add(iter_referenced_shared_objects(instances))
    return instances


def _uncollected_referenced_pks(
    instances: list[Model],
    seen: set[tuple[type[Model], object]],
    model: type[Model],
) -> set[object]:
    """Return the PKs of ``model`` instances referenced by a collected instance but not yet collected."""
    return {
        target.pk
        for instance in list(instances)
        for target in _iter_relational_reference_targets(instance)
        if type(target) is model and (model, target.pk) not in seen
    }


def _includable_indicator_ids(pks: set[object], plan: Plan) -> set[object]:
    """Drop indicators owned by another plan (their data is that tenant's, not ours)."""
    other_plan_ids = set(
        Indicator.objects.filter(id__in=pks, plans__isnull=False).exclude(plans=plan).values_list('id', flat=True)
    )
    return pks - other_plan_ids


def _includable_dimension_ids(pks: set[object], plan: Plan) -> set[object]:
    """Drop dimensions owned by another plan (linked via PlanDimension to a different plan only)."""
    other_plan_ids = set(
        Dimension.objects.filter(id__in=pks, plans__isnull=False)
        .exclude(plans__plan=plan)
        .values_list('id', flat=True)
    )
    return pks - other_plan_ids


def _add_referenced_indicator_graph(
    plan: Plan,
    instances: list[Model],
    add: Callable[[Generator[Model] | list[Model]], list[Model]],
    seen: set[tuple[type[Model], object]],
) -> None:
    """
    Include indicators (and the dimensions they use) referenced by exported rows but not owned.

    Exported ``ActionIndicator``/``IndicatorCategoryThrough`` rows can reference indicators that
    are not part of ``plan.indicators`` (e.g. indicators attached to an action but never added
    to the plan). Pulling those indicators in via ``INDICATOR_CLONE_STRUCTURE`` in turn pulls in
    their values, which reference dimension categories -- so dimensions must be closed over too.

    Runs to a fixpoint, since each newly added indicator or dimension can reference further
    ones. Indicators or dimensions owned by a *different* plan are skipped, preserving tenant
    isolation: only orphaned or this-plan objects are pulled in.
    """
    while True:
        indicator_ids = _includable_indicator_ids(_uncollected_referenced_pks(instances, seen, Indicator), plan)
        dimension_ids = _includable_dimension_ids(_uncollected_referenced_pks(instances, seen, Dimension), plan)
        if not indicator_ids and not dimension_ids:
            return
        added: list[Model] = []
        for indicator in Indicator.objects.filter(id__in=indicator_ids):
            added += add(_iter_clone_structure_instances(indicator, INDICATOR_CLONE_STRUCTURE))
            if indicator.dataset_schema is not None:
                added += add(_iter_clone_structure_instances(indicator.dataset_schema, DATASET_SCHEMA_CLONE_STRUCTURE))
        for dimension in Dimension.objects.filter(id__in=dimension_ids):
            added += add(_iter_clone_structure_instances(dimension, DIMENSION_CLONE_STRUCTURE))
        if not added:  # pragma: no cover - safety net against a non-converging loop
            return


def _add_referenced_media(
    instances: list[Model],
    add: Callable[[Generator[Model] | list[Model]], list[Model]],
) -> None:
    """
    Include images/documents referenced by exported content but outside the plan's collections.

    Media is otherwise collected by collection membership (``iter_plan_media_instances``), but
    pages and rich-text/StreamField bodies can reference images and documents that live in
    other collections (e.g. a page header image, an embedded image). We find those via forward
    references and Wagtail's ``ReferenceIndex``, and also pull in their collection rows so the
    collection FK does not dangle.
    """
    media_models = (AplansImage, AplansDocument)
    targets: list[Model] = []
    snapshot = list(instances)
    for instance in snapshot:
        targets.extend(t for t in _iter_relational_reference_targets(instance) if isinstance(t, media_models))
        for reference in ReferenceIndex.get_references_for_object(instance):
            model = reference.to_content_type.model_class()
            if model in media_models:
                referenced = model.objects.filter(pk=reference.to_object_id).first()
                if referenced is not None:
                    targets.append(referenced)
    added_media = add(targets)
    # Wagtail images/documents always have a (non-nullable) collection; pull in any that
    # aren't already present so the collection FK does not dangle.
    add([media.collection for media in added_media if isinstance(media, media_models)])


def serialize_plan(
    plan: Plan,
    *,
    structure: CloneStructure = EXPORT_PLAN_STRUCTURE,
    include_indicators: bool = True,
    include_referenced_shared_objects: bool = False,
    indent: int | None = 2,
) -> str:
    """
    Serialize a single plan's data to a JSON string in Django's ``dumpdata`` format.

    Natural foreign keys keep ``ContentType``/``Permission``/``Locale`` references portable
    across databases where those primary keys differ.
    """
    instances = collect_export_instances(
        plan,
        structure=structure,
        include_indicators=include_indicators,
        include_referenced_shared_objects=include_referenced_shared_objects,
    )
    return serializers.serialize(
        'json',
        instances,
        indent=indent,
        use_natural_foreign_keys=True,
    )


def _referenced_persons(instances: list[Model]) -> Generator[Person]:
    """Yield the distinct Person objects referenced by a foreign key on any collected instance."""
    seen: set[object] = set()
    for instance in instances:
        for fk in get_foreign_keys(instance):
            if fk.related_model is not Person:
                continue
            person = getattr(instance, fk.name)
            if person is None or person.pk in seen:
                continue
            seen.add(person.pk)
            yield person


def build_media_manifest(instances: list[Model]) -> dict[str, list[str]]:
    """
    Build a manifest of object-storage keys for the media referenced by an export.

    The JSON dump only references file paths; the binary files must be copied separately (e.g.
    with ``rclone``). Returns lists of storage keys for images, documents and person avatars.
    """
    images = [i.file.name for i in instances if isinstance(i, AplansImage) and i.file and i.file.name]
    documents = [d.file.name for d in instances if isinstance(d, AplansDocument) and d.file and d.file.name]
    avatars = [person.image.name for person in _referenced_persons(instances) if person.image and person.image.name]
    return {'images': images, 'documents': documents, 'avatars': avatars}
