from __future__ import annotations

from collections import defaultdict
from functools import cache
from typing import TYPE_CHECKING, Any, cast

from django.apps import apps
from django.db.models import Model
from django.db.models.signals import post_delete
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel, get_all_child_relations
from wagtail.models import DraftStateMixin, Page, Revision

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, MutableMapping, Sequence

    from django.db.models import ForeignKey

logger = logger.bind(name='aplans.draft_references')

_DISPATCH_UID = 'aplans_clear_deleted_child_from_draft'


def keeps_children_in_drafts(model: type[Model]) -> bool:
    """
    Return whether drafts of `model` contain serialized copies of its child objects.

    Wagtail pages are left out: their revision content holds data that Wagtail maintains
    itself, such as comments, and their editor has its own rules for it.
    """
    return issubclass(model, DraftStateMixin) and issubclass(model, ClusterableModel) and not issubclass(model, Page)


@cache
def draft_parent_relations(model: type[Model]) -> list[ParentalKey[Any, Any]]:
    """Return the `ParentalKey`s of `model` that point to a model keeping drafts."""
    return [
        field
        for field in model._meta.get_fields()
        if isinstance(field, ParentalKey) and keeps_children_in_drafts(field.related_model)
    ]


def clear_deleted_child_from_draft(sender: type[Model], instance: Any, **_kwargs: Any) -> None:
    """
    Drop the primary key of a just-deleted child object from its parent's draft.

    A draft is a serialized copy of the parent and all of its child objects, so it keeps
    referring to a child that has been deleted from the published version in the meantime.
    The edit view builds its form from the draft, and the formset rejects the primary key of
    a row that is no longer in the database, which fails the whole form with a message that
    says nothing about the cause. Clearing the primary key turns the stale row into a new
    one, so publishing the draft recreates the child object instead of trying to update a
    deleted one.
    """
    for relation in draft_parent_relations(sender):
        _clear_child_pk(relation, instance)


def _clear_child_pk(relation: ParentalKey[Any, Any], child: Any) -> None:
    parent_id = getattr(child, relation.attname)
    if parent_id is None:
        return
    parent_model = relation.related_model
    latest_revision = parent_model._base_manager.filter(pk=parent_id).values('latest_revision_id')
    revision = Revision.objects.filter(pk__in=latest_revision).first()
    if revision is None:
        return

    relation_name = relation.remote_field.get_accessor_name()
    assert relation_name is not None
    stale = [item for item in revision.content.get(relation_name, []) if item.get('pk') == child.pk]
    if not stale:
        return

    for item in stale:
        item['pk'] = None
    revision.save(update_fields=['content'])
    logger.info(
        f'Cleared reference to deleted {child._meta.label} {child.pk} from {relation_name} in revision {revision.pk} '
        f'of {parent_model._meta.label} {parent_id}',
    )


def register_draft_reference_cleanup() -> None:
    """Connect `clear_deleted_child_from_draft` for every model that can appear in a draft as a child object."""
    for model in apps.get_models():
        if not draft_parent_relations(model):
            continue
        post_delete.connect(clear_deleted_child_from_draft, sender=model, dispatch_uid=_DISPATCH_UID)


@cache
def _reference_fields(model: type[Model]) -> tuple[ForeignKey[Any, Any], ...]:
    """Return the fields of `model` that hold a reference to another row."""
    return tuple(cast('ForeignKey[Any, Any]', field) for field in model._meta.fields if field.remote_field is not None)


ExistingPks = dict[type[Model], set[Any]]


def _is_missing(field: ForeignKey[Any, Any], data: Mapping[str, Any], existing: ExistingPks) -> bool:
    pk = data.get(field.name)
    return pk is not None and pk not in existing[field.related_model]


def _referenced_pks(model: type[Model], contents: Iterable[Mapping[str, Any]]) -> dict[type[Model], set[Any]]:
    referenced: dict[type[Model], set[Any]] = defaultdict(set)

    def collect(fields: tuple[ForeignKey[Any, Any], ...], data: Mapping[str, Any]) -> None:
        for field in fields:
            pk = data.get(field.name)
            if pk is not None:
                referenced[field.related_model].add(pk)

    child_relations = get_all_child_relations(model)
    for content in contents:
        collect(_reference_fields(model), content)
        for relation in child_relations:
            for row in content.get(relation.get_accessor_name()) or ():
                collect(_reference_fields(relation.related_model), row)
    return referenced


def strip_missing_references(model: type[Model], contents: Sequence[MutableMapping[str, Any]]) -> None:
    """
    Drop references to rows that no longer exist from serialized `model` instances, in place.

    `from_serializable_data(check_fks=True)` does this one reference at a time, at the cost of
    a query each, which is why callers that deserialize many revisions at once pass
    `check_fks=False`. This leaves behind the same data as a checked deserialization would,
    using one query per referenced model for the whole batch: a null where the field allows
    it, and no row at all for a child object that cannot live without its target.

    Without it a reference to a deleted row survives into the deserialized object, and
    whichever resolver touches it raises `DoesNotExist`.
    """
    existing: ExistingPks = {
        related_model: set(related_model._base_manager.filter(pk__in=pks).values_list('pk', flat=True))
        for related_model, pks in _referenced_pks(model, contents).items()
    }
    for content in contents:
        _strip_content_references(model, content, existing)


def _strip_content_references(model: type[Model], content: MutableMapping[str, Any], existing: ExistingPks) -> None:
    for field in _reference_fields(model):
        if field.null and _is_missing(field, content, existing):
            content[field.name] = None

    for relation in get_all_child_relations(model):
        relation_name = relation.get_accessor_name()
        rows: list[dict[str, Any]] | None = content.get(relation_name)
        if not rows:
            continue
        fields = _reference_fields(relation.related_model)
        kept = (_row_without_missing_references(row, fields, existing) for row in rows)
        content[relation_name] = [row for row in kept if row is not None]


def _row_without_missing_references(
    row: dict[str, Any], fields: tuple[ForeignKey[Any, Any], ...], existing: ExistingPks
) -> dict[str, Any] | None:
    """Return `row` with unresolvable nullable references cleared, or None if it needs one that is gone."""
    kept = row
    for field in fields:
        if not _is_missing(field, row, existing):
            continue
        if not field.null:
            return None
        if kept is row:
            kept = dict(row)
        kept[field.name] = None
    return kept
