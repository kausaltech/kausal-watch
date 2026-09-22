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
    from collections.abc import Iterable, Iterator, Mapping, MutableMapping, Sequence

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
def draft_parent_paths(model: type[Model]) -> tuple[tuple[ParentalKey[Any, Any], ...], ...]:
    """
    Return every chain of `ParentalKey`s leading from `model` up to a model that keeps drafts.

    A chain has more than one link for a model nested deeper in the cluster, such as an
    assignment of an action task, which the draft of an action holds inside its task.
    """
    return tuple(_parent_paths(model, ()))


def _parent_paths(model: type[Model], seen: tuple[type[Model], ...]) -> Iterator[tuple[ParentalKey[Any, Any], ...]]:
    if model in seen:  # a cycle of parental keys cannot lead anywhere new
        return
    for field in model._meta.get_fields():
        if not isinstance(field, ParentalKey):
            continue
        if keeps_children_in_drafts(field.related_model):
            yield (field,)
            continue
        for path in _parent_paths(field.related_model, (*seen, model)):
            yield (field, *path)


def clear_deleted_child_from_draft(sender: type[Model], instance: Any, origin: Any = None, **_kwargs: Any) -> None:
    """
    Drop the primary key of a just-deleted child object from its parent's draft.

    A draft is a serialized copy of the parent and all of its child objects, so it keeps
    referring to a child that has been deleted from the published version in the meantime.
    The edit view builds its form from the draft, and the formset rejects the primary key of
    a row that is no longer in the database, which fails the whole form with a message that
    says nothing about the cause. Clearing the primary key turns the stale row into a new
    one, so publishing the draft recreates the child object instead of trying to update a
    deleted one.

    A child that went away with a cascade is left alone: whatever it points at is gone as
    well, so deserialization drops the row whichever way the draft is read. Repairing those
    would cost a query per deleted row, and deleting one indicator or organization can
    cascade to a row in every action that refers to it.
    """
    if not _was_deleted_directly(sender, instance, origin):
        return
    for path in draft_parent_paths(sender):
        _clear_child_pk(path, instance)


def _was_deleted_directly(sender: type[Model], instance: Any, origin: Any) -> bool:
    """Tell whether `delete()` was called on the child itself rather than on something that cascaded to it."""
    if origin is None:  # a sender that does not report where the deletion came from
        return True
    if origin is instance:  # Model.delete()
        return True
    return getattr(origin, 'model', None) is sender  # QuerySet.delete()


def _clear_child_pk(path: tuple[ParentalKey[Any, Any], ...], child: Any) -> None:
    owner_id = _draft_owner_id(path, child)
    if owner_id is None:
        return
    owner_model = path[-1].related_model
    latest_revision = owner_model._base_manager.filter(pk=owner_id).values('latest_revision_id')
    revision = Revision.objects.filter(pk__in=latest_revision).first()
    if revision is None:
        return

    relation_names = [link.remote_field.get_accessor_name() for link in reversed(path)]
    stale = [row for row in _rows_at(revision.content, relation_names) if row.get('pk') == child.pk]
    if not stale:
        return

    for row in stale:
        row['pk'] = None
    revision.save(update_fields=['content'])
    logger.info(
        f'Cleared reference to deleted {child._meta.label} {child.pk} from {".".join(relation_names)} in revision '
        f'{revision.pk} of {owner_model._meta.label} {owner_id}',
    )


def _draft_owner_id(path: tuple[ParentalKey[Any, Any], ...], child: Any) -> Any:
    """Follow the chain up from the deleted child to the primary key of the model keeping the draft."""
    owner_id = getattr(child, path[0].attname)
    for link in path[1:]:
        if owner_id is None:
            return None
        owner_id = link.model._base_manager.filter(pk=owner_id).values_list(link.attname, flat=True).first()
    return owner_id


def _rows_at(content: Mapping[str, Any], relation_names: Sequence[str | None]) -> list[dict[str, Any]]:
    """Return the serialized rows that `relation_names` leads to, descending one relation at a time."""
    rows: list[Any] = [content]
    for name in relation_names:
        rows = [nested for row in rows for nested in (row.get(name) or ())]
    return rows


def register_draft_reference_cleanup() -> None:
    """Connect `clear_deleted_child_from_draft` for every model that can appear in a draft as a child object."""
    for model in apps.get_models():
        if not draft_parent_paths(model):
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

    def walk(child_model: type[Model], data: Mapping[str, Any]) -> None:
        collect(_reference_fields(child_model), data)
        for relation in get_all_child_relations(child_model):
            for row in data.get(relation.get_accessor_name()) or ():
                walk(relation.related_model, row)

    for content in contents:
        walk(model, content)
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
        child_model = relation.related_model
        fields = _reference_fields(child_model)
        kept: list[dict[str, Any]] = []
        for row in rows:
            stripped = _row_without_missing_references(row, fields, existing)
            if stripped is None:
                continue
            # A child can hold children of its own, such as the assignments of an action task
            _strip_content_references(child_model, stripped, existing)
            kept.append(stripped)
        content[relation_name] = kept


def _row_without_missing_references(
    row: dict[str, Any], fields: tuple[ForeignKey[Any, Any], ...], existing: ExistingPks
) -> dict[str, Any] | None:
    """
    Return a copy of `row` with unresolvable nullable references cleared, or None to drop it.

    The copy is unconditional because the caller descends into the result and replaces the
    lists of its children, and `row` itself belongs to the revision this must not write to.
    """
    kept = dict(row)
    for field in fields:
        if not _is_missing(field, row, existing):
            continue
        if not field.null:
            return None
        kept[field.name] = None
    return kept
