from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING, Any

from django.apps import apps
from django.db.models.signals import post_delete
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel
from wagtail.models import DraftStateMixin, Page, Revision

from loguru import logger

if TYPE_CHECKING:
    from django.db.models import Model

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
def draft_parent_relations(model: type[Model]) -> list[ParentalKey]:
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


def _clear_child_pk(relation: ParentalKey, child: Any) -> None:
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
