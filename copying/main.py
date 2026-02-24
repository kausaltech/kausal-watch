from __future__ import annotations

import dataclasses
from collections.abc import Callable, Generator, Iterable
from contextlib import ExitStack
from copy import copy as shallow_copy
from functools import singledispatchmethod, wraps
from itertools import chain
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar
from uuid import uuid4

import wagtail.signal_handlers
from django.contrib.auth.models import Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Count, Field, ForeignKey, Manager, ManyToOneRel, Model, Q, signals
from modelcluster.fields import ParentalKey
from modelcluster.models import ClusterableModel, get_all_child_relations
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page, Revision, RevisionMixin, Site
from wagtail.models.i18n import Locale
from wagtail.models.media import Collection
from wagtail.models.reference_index import ReferenceIndex

from loguru import logger
from relations_iterator import AbstractVisitor, ConfigurableRelationTree, RelationTreeIterator, TreeNode, clone  # type: ignore

from actions.models.action import Action
from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryType, CommonCategory, CommonCategoryType
from actions.models.plan import Plan
from actions.signals import create_notification_settings, create_plan_features_and_sync_group_permissions
from admin_site.models import Client
from content.apps import create_site_general_content
from copying.utils import (
    get_foreign_keys,
    get_generic_foreign_keys,
    temp_disconnect_signal,
    update_rich_text_reference_in_field,
    update_streamfield_block,
)
from documentation.models import DocumentationRootPage
from documents.models import AplansDocument
from images.models import AplansImage
from indicators.models.common_indicator import CommonIndicator
from indicators.models.dimensions import Dimension
from indicators.models.indicator import Indicator, IndicatorLevel
from indicators.models.metadata import Quantity, Unit
from orgs.models import Organization
from pages.models import PlanRootPage
from people.models import Person
from users.models import User

if TYPE_CHECKING:
    from wagtail.documents.models import AbstractDocument
    from wagtail.images.models import AbstractImage

P = ParamSpec('P')
R = TypeVar('R')

type CloneStructure = dict[str, CloneStructure]

# TODO: Models from other apps: budget, feedback, etc.
PLAN_CLONE_STRUCTURE: CloneStructure = {
    'action_decision_levels': {},
    'action_dependency_roles': {},
    'action_impacts': {},
    'action_implementation_phases': {},
    'action_schedules': {},
    'action_statuses': {},
    'features': {},
    'actions': {
        'action_category_through': {},
        'action_monitoring_quality_points_through': {},
        'action_schedule_through': {},
        'contact_persons': {},
        'dependent_relationships': {},
        'impact_groups': {},
        'links': {},
        'related_actions_through': {},
        'related_indicators': {},
        'responsible_parties': {},
        'status_updates': {},
        'tasks': {},
    },
    'built_in_field_customizations': {},
    'category_types': {
        'categories': {
            'indicator_category_through': {},  # We don't copy the indicators themselves
        },
        'levels': {},
    },
    'clients': {},
    # 'domains': {},  # deliberately don't copy domains because hostname + base path should be unique
    'general_admins_ordered': {},
    'general_content': {},
    'impact_groups': {},
    'indicator_levels': {},  # We copy the indicators themselves separately and optionally
    'notification_settings': {},
    'plan_common_category_types_through': {},
    'plan_related_organizations_through': {},
    'public_site_viewers': {},
    'report_types': {
        # Deliberately don't copy reports because (a) the contained action snapshots refer to instances from the
        # original plan within the serialized data, and (b) it might be justifiable for many use cases to skip copying
        # reports. We could do something about (a) by meddling with the serialized data, but it's going to be an
        # error-prone ordeal, so maybe this is fine for now.
        # 'reports': {
        #     'action_snapshots': {},  # As we don't copy `action_version`, original action will be linked to snapshot
        # },
    },
    'scenarios': {},
    # Note that `Dimension` instances are copied separately when `copy_indicators` is true.
    'dimensions': {},  # copies through model (`PlanDimension`) instances, not `Dimension` instances
}

ATTRIBUTE_TYPE_CLONE_STRUCTURE: CloneStructure = {
    'choice_options': {},
    'category_choice_attributes': {},
    'choice_attributes': {},
    'choice_with_text_attributes': {},
    'numeric_value_attributes': {},
    'text_attributes': {},
    'rich_text_attributes': {},
}

INDICATOR_CLONE_STRUCTURE: CloneStructure = {
    # We deliberately exclude the following fields as they seem legacy:
    # - datasets
    # - latest_graph

    # We do not copy the following fields `levels` field as they are taken care of by `PLAN_CLONE_STRUCTURE`:
    # - levels (due to indicator_levels)
    # - related_actions (due to actions -> related_indicators)

    'contact_persons': {},
    'values': {
        'category_links': {},  # copies through model instances, not `DimensionCategory` instances
    },
    # 'related_actions': {},  # ActionIndicator instances are already copied in PLAN_CLONE_STRUCTURE
    'related_causes': {},
    # If we included not only `related_causes` but also `related_effects`, we'd try to copy ActionIndicator instances
    # twice as it's already done due to `related_causes`.
    'goals': {},
    'dimensions': {},  # copies through model (`IndicatorDimension`) instances, not `Dimension` instances
}

DIMENSION_CLONE_STRUCTURE: CloneStructure = {
    'categories': {},
}

# Models that are not scoped by a plan and thus deliberately excluded from copying. References to these models are
# skipped in `UpdateReferencesVisitor.get_references()` and warnings are suppressed in `update_reference()`.
MODELS_NOT_COPIED = [
    Client,
    CommonCategory,
    CommonCategoryType,
    CommonIndicator,
    ContentType,
    Group,
    Locale,
    Organization,
    Person,
    Quantity,
    Unit,
    User,
]


class CloneVisitor(AbstractVisitor):
    """Visit a tree node and create a copy of its instance, keeping track of which copy belongs to which instance."""

    # Map (model, PK) of copied instance to instance copy created when visiting nodes
    copies: dict[tuple[type[Model], Any], Model]
    # Map (model, PK) of an original instance to a dict that maps a field from that instance to a related object
    removed_links: dict[tuple[type[Model], Any], dict[str, Model]]
    # Each plan must have a site with a unique hostname + port
    site_hostname: str
    # Suffix to add to model fields if they exist; allows for distinguishing the copies in an easy way
    copy_name_suffix: str
    # Identifier and name for the copy of the plan; overrides any suffix stuff
    plan_identifier: str | None
    plan_name: str | None
    version_name: str | None
    supersede_original_plan: bool
    supersede_original_actions: bool

    def __init__(
        self,
        site_hostname: str,
        plan_identifier: str | None = None,
        plan_name: str | None = None,
        copy_name_suffix: str | None = None,
        version_name: str | None = None,
        supersede_original_plan: bool = False,
        supersede_original_actions: bool = False,
    ):
        self.site_hostname = site_hostname
        self.plan_identifier = plan_identifier
        self.plan_name = plan_name
        if copy_name_suffix:
            self.copy_name_suffix = ' ' + copy_name_suffix
        else:
            self.copy_name_suffix = ''
        self.version_name = version_name
        self.copies = {}
        self._copy_keys: set[tuple[type[Model], Any]] = set()
        self._copy_to_original_pk: dict[tuple[type[Model], Any], Any] = {}
        self.removed_links = {}
        self.supersede_original_plan = supersede_original_plan
        self.supersede_original_actions = supersede_original_actions

    def has_copy(self, instance: Model) -> bool:
        """Return true if a copy has been created for the given instance."""
        return (type(instance), instance.pk) in self.copies

    def is_copy(self, instance: Model) -> bool:
        """Return true if the given instance is a copy of something."""
        return (type(instance), instance.pk) in self._copy_keys

    def get_copy[M: Model](self, instance: M) -> M:
        """Get the copy that has been created for the given instance."""
        copy = self.copies[(type(instance), instance.pk)]
        assert type(copy) is type(instance)
        assert isinstance(copy, type(instance))  # implied by previous line, but apparently mypy doesn't figure this out
        return copy

    def _get_original_pk(self, copy: Model) -> Any:
        """Get the PK of the original instance for the given copy."""
        return self._copy_to_original_pk[(type(copy), copy.pk)]

    def register_copy[M: Model](self, original: M, copy: M):
        """
        Store that `copy` is a copy of `original`.

        This allows us to later get the copy for the original using self.get_copy(). The clone visitor registers all
        copies it creates itself, but if you create copies outside of the clone visitor, you can register them here.
        """
        key = (type(original), original.pk)
        assert key not in self.copies
        assert not self.has_copy(original)  # should be the same as the previous line, but you never know
        assert not self.is_copy(copy)  # `copy` can't be a copy of multiple originals
        self.copies[key] = copy
        self._copy_keys.add((type(copy), copy.pk))
        self._copy_to_original_pk[(type(copy), copy.pk)] = original.pk

    def visit(self, node: TreeNode):
        """
        Create a copy of the instance of the given node.

        Behavior can be customized for each instance type using the hooks `pre_visit` and `save_copy`.
        """
        original_instance = shallow_copy(node.instance)
        self.pre_visit(node.instance)
        node.instance.pk = None
        node.instance._state.adding = True
        if node.parent is not None:
            parent_joining_field, instance_joining_field = node.relation.get_joining_fields()[0]
            setattr(
                node.instance,
                instance_joining_field.attname,
                parent_joining_field.value_from_object(node.parent.instance)
            )
        self.save_copy(node.instance)
        logger.info(f"Created {type(node.instance).__name__} {node.instance.pk}: {node.instance}")
        assert isinstance(node.instance, node.model_class)
        self.register_copy(original_instance, node.instance)
        self.post_visit(original_instance, node.instance)

    def remove_link(self, instance: Model, field: str):
        """
        Temporarily remove a reference from `instance`, e.g., to break cycles.

        Sets the field to `None`. After cloning, you can call `restore_removed_links()` to restore the link by setting
        it to the cloned version of the original value of the field.
        """
        related_object = getattr(instance, field)
        if related_object:
            key = (type(instance), instance.pk)
            fields = self.removed_links.setdefault(key, {})
            assert field not in fields
            fields[field] = related_object
            setattr(instance, field, None)

    def restore_removed_links(self):
        """
        Restore links that have been removed using `remove_link()`.

        Each restored link will point to the copy of the original link target.
        """
        for (model, pk), links in self.removed_links.items():
            update_fields = []
            copy = self.copies[(model, pk)]
            for field, related_object in links.items():
                assert getattr(copy, field) is None
                related_copy = self.get_copy(related_object)
                setattr(copy, field, related_copy)
                update_fields.append(field)
            if update_fields:
                copy.save(update_fields=update_fields)

    def prepare_instance_for_copy(self, instance):
        if hasattr(instance, 'name'):
            instance.name += self.copy_name_suffix
        if hasattr(instance, 'uuid'):
            instance.uuid = uuid4()
        if hasattr(instance, 'copy_of_id'):
            instance.copy_of_id = instance.id

    @singledispatchmethod
    def pre_visit(self, instance) -> None:
        """
        Prepare `instance` before copying it.

        Can be overloaded for different types of instances. You may want to call `prepare_instance_for_copy()` in each
        overloading method.
        """
        self.prepare_instance_for_copy(instance)

    @pre_visit.register
    def _(self, instance: AttributeType) -> None:
        self.prepare_instance_for_copy(instance)
        # We need to change the reference to the plan *before* saving. It's not enough to do it afterwards with
        # `UpdateReferencesVisitor`. This is because the `AutoSlugField` for `identifier` in `AttributeType` has
        # `always_update=True` and is unique per plan. So when saving the copy, it references the same plan as the
        # original, thus getting a suffix appended to the slug to make it unique.
        instance.scope = self.get_copy(instance.scope)  # type: ignore

    @pre_visit.register
    def _(self, instance: Plan) -> None:
        self.prepare_instance_for_copy(instance)
        if self.plan_identifier:
            instance.identifier = self.plan_identifier
        if self.plan_name:
            instance.name = self.plan_name
        if self.version_name:
            instance.version_name = self.version_name
        # Temporarily break cycles; to be restored after everything has been copied
        self.remove_link(instance, 'primary_action_classification')
        self.remove_link(instance, 'secondary_action_classification')
        # Groups will be created in Plan.save()
        instance.admin_group = None
        instance.contact_person_group = None
        # Collection must have been copied before plan
        assert instance.root_collection
        instance.root_collection = self.get_copy(instance.root_collection)
        # Site must have been copied before plan
        assert instance.site
        site_copy = self.get_copy(instance.site)
        assert site_copy
        instance.site = site_copy
        instance.site_url = f'https://{site_copy.hostname}'
        # TODO: Ideally it should be configurable whether 'published_at` is reset
        instance.published_at = None

    @pre_visit.register
    def _(self, instance: Site) -> None:
        self.prepare_instance_for_copy(instance)
        instance.hostname = self.site_hostname

    @singledispatchmethod
    def save_copy(self, instance) -> None:
        """Persist the copy `instance` in the database."""
        instance.save()

    @save_copy.register
    def _(self, instance: Collection) -> None:
        # `instance` still has the path of the collection it was copied from
        parent = instance.get_parent()
        assert parent
        instance.path = ''
        parent.add_child(instance=instance)

    @save_copy.register
    def _(self, instance: Category) -> None:
        instance.save(skip_page_synchronization=True)

    @save_copy.register
    def _(self, instance: CategoryType) -> None:
        instance.save(skip_page_synchronization=True)

    @singledispatchmethod
    def post_visit(self, original, copy) -> None:
        """Do some stuff after creating the copy `copy` of `instance` and persisting it to the database."""
        pass

    @post_visit.register
    def _(self, original: Plan, copy: Plan) -> None:
        if self.supersede_original_plan:
            if original.superseded_by:
                raise ValueError(
                    f"Cannot supersede plan '{original}': already superseded by '{original.superseded_by}'"
                )
            original.superseded_by = copy
            original.save(update_fields=['superseded_by'])

    @post_visit.register
    def _(self, original: Action, copy: Action) -> None:
        if self.supersede_original_actions:
            if original.superseded_by:
                raise ValueError(
                    f"Cannot supersede action '{original}': already superseded by '{original.superseded_by}'"
                )
            original.superseded_by = copy
            original.save(update_fields=['superseded_by'])


class UpdateReferencesVisitor(AbstractVisitor):
    """Update references to objects that have been copied so that they point to the created copies."""

    def __init__(self, clone_visitor: CloneVisitor):
        # The object `clone_visitor` will be used for associating instances with their copies.
        self.clone_visitor = clone_visitor

    def update_instance(self, instance: Model, save: bool = True, skip_page_draft: bool = False) -> bool:
        """
        Update all references from `instance` to objects that have been copied to point to the copies.

        Returns true if and only if the instance was updated, regardless of whether it was saved.
        """
        logger.trace(f"Update references of {type(instance).__name__} {instance.pk}: {instance}")
        update_fields = []
        update_fields += self.update_cluster_related_objects(instance)
        logger.info(f"Updating foreign keys of {type(instance).__name__} {instance.pk}: {instance}")
        update_fields += self.update_foreign_keys(instance)
        update_fields += self.update_indexed_references(instance)
        if isinstance(instance, Page) and not skip_page_draft:
            logger.info(f"Updating page draft of {type(instance).__name__} {instance.pk}: {instance}")
            update_fields += self.update_page_draft(instance)
        # Save changes
        if update_fields and save:
            save_kwargs: dict[str, Any] = {'update_fields': update_fields}
            # Ugly ad-hoc workaround :(
            if isinstance(instance, (Category, CategoryType)):
                save_kwargs['skip_page_synchronization'] = True
            instance.save(**save_kwargs)
            logger.info(
                f"Updated references in {len(update_fields)} fields of "
                f"{type(instance).__name__} {instance.pk}: {instance}"
            )
        return bool(update_fields)

    def _get_references(
        self, instance: Model, exclude_fields: Iterable[str] | None = None
    ) -> Generator[Field | GenericForeignKey]:
        if exclude_fields is None:
            exclude_fields = []
        for fk in get_foreign_keys(instance):
            if fk.name not in exclude_fields and fk.related_model not in MODELS_NOT_COPIED:
                yield fk
        for gfk in get_generic_foreign_keys(instance):
            if gfk.name not in exclude_fields:
                yield gfk

    @singledispatchmethod
    def get_references(self, instance: Model) -> Generator[Field | GenericForeignKey]:
        return self._get_references(instance)

    @get_references.register
    def _(self, instance: Action) -> Generator[Field | GenericForeignKey]:
        return self._get_references(instance, exclude_fields=['copy_of'])

    @get_references.register
    def _(self, instance: Plan) -> Generator[Field | GenericForeignKey]:
        return self._get_references(instance, exclude_fields=['copy_of'])

    @get_references.register
    def _(self, instance: Page) -> Generator[Field | GenericForeignKey]:
        # Pages are copied via Wagtail's Page.copy(), which handles certain fields internally. These objects are not
        # registered in the clone visitor, so skip them to avoid spurious warnings.
        return self._get_references(instance, exclude_fields=[
            'page_ptr', 'latest_revision', 'live_revision', 'staticpage_ptr',
        ])

    def update_extractable_references(self, instance: Model) -> bool:
        updated = False
        for field in instance._meta.get_fields():
            if isinstance(field, Field) and hasattr(field, 'extract_references'):
                value = field.value_from_object(instance)
                for to_model, to_object_id, _, content_path in field.extract_references(value):
                    to_object = to_model.objects.get(id=to_object_id)
                    updated_this = self.update_reference(
                        from_object=instance,
                        to_object=to_object,
                        source_field=field,
                        content_path=f'{field.name}.{content_path}',
                    )
                    if updated_this:
                        updated = True
        return updated

    def update_cluster_related_object(self, parent: Model, cro: Model) -> bool:
        updated = False
        try:
            cro_copy = self.clone_visitor.get_copy(cro)
        except KeyError:
            if cro.pk is not None and not self.clone_visitor.is_copy(cro):
                # Probably there is no copy because the model instance that `cro` originally corresponded to no
                # longer exists in the database.
                logger.warning(
                    f"In cluster related objects of {type(parent).__name__} {parent.pk}: Could not find "
                    f"copy for {type(cro).__name__} {cro.pk}: {cro}"
                )
                cro.pk = None
                updated = True
        else:
            assert cro.pk != cro_copy.pk
            cro.pk = cro_copy.pk
            updated = True
            logger.trace(
                f"In cluster related objects of {type(parent).__name__} {parent.pk}: Set primary key "
                f"of {type(cro).__name__} {cro.pk} to: {cro_copy.pk}"
            )

        updated_extractable_refs = self.update_extractable_references(cro)
        if updated_extractable_refs:
            updated = True

        for fk in self.get_references(cro):
            related_object = getattr(cro, fk.name)
            if related_object:
                # `related_object` may or may not be a copy already depending on what some other code did before
                if self.clone_visitor.has_copy(related_object):
                    related_object = self.clone_visitor.get_copy(related_object)
                setattr(cro, fk.name, related_object)
                if hasattr(fk, 'fk_field'):
                    id_field = fk.fk_field
                else:
                    id_field = fk.attname
                if getattr(cro, id_field) != related_object.id:
                    setattr(cro, id_field, related_object.id)
                    updated = True
                    logger.trace(
                        f"In cluster related objects of {type(parent).__name__} {parent.pk}: Set foreign key "
                        f"'{fk.name}' of {type(cro).__name__} {parent.pk} to: {related_object.pk}"
                    )
        return updated

    def update_cluster_related_objects(self, instance: Model) -> list[str]:
        update_fields = set()
        for field_name, child_object in get_cluster_related_objects(instance):
            updated = self.update_cluster_related_object(instance, child_object)
            if updated:
                update_fields.add(field_name)
        return list(update_fields)

    def update_foreign_keys(self, instance: Model) -> list[str]:
        update_fields = []
        for fk in self.get_references(instance):
            assert hasattr(fk, 'name')
            related_object = getattr(instance, fk.name)
            if related_object:
                if related_object._meta.model in MODELS_NOT_COPIED:
                    continue
                try:
                    copy = self.clone_visitor.get_copy(related_object)
                except KeyError:
                    if self.clone_visitor.is_copy(related_object):
                        logger.trace(
                            f"Trying to update foreign key '{fk.name}' of {type(instance).__name__} {instance.pk} "
                            f"that is already a copy: {type(related_object).__name__} {related_object.pk}"
                        )
                    else:
                        logger.warning(
                            f"Could not find copy for {type(related_object).__name__} {related_object.pk} "
                            f"when trying to update foreign key '{fk.name}' of {type(instance).__name__} {instance.pk}"
                        )
                    continue
                logger.trace(f"Set foreign key '{fk.name}' of {type(instance).__name__} {instance.pk} to: {copy.pk}")
                setattr(instance, fk.name, copy)
                if isinstance(fk, GenericForeignKey):
                    # Technically we'd also need to update fk.ct_field, but content types don't change by copying
                    update_fields.append(fk.fk_field)
                else:
                    update_fields.append(fk.name)
        return update_fields

    def update_reference(self, from_object: Model, to_object: Model, source_field: Field, content_path: str) -> bool:
        """
        Update the reference to `to_object` in the field `source_field` of `from_object` at `content_path`.

        Returns true if and only if the instance was updated.
        """

        if to_object._meta.model in MODELS_NOT_COPIED:
            return False

        try:
            copy = self.clone_visitor.get_copy(to_object)
        except KeyError:
            if self.clone_visitor.is_copy(to_object):
                logger.trace(
                    f"Trying to update reference in {type(from_object).__name__} {from_object.pk} at path "
                    f"'{content_path}' that is already a copy: {type(to_object).__name__} {to_object.pk}"
                )
            else:
                logger.warning(
                    f"Cannot update reference in {type(from_object).__name__} {from_object.pk} at path '{content_path}': "
                    f"Could not find copy for {type(to_object).__name__} {to_object.pk}"
                )
            return False

        if isinstance(source_field, StreamField):
            # We can't use apply_changes_to_raw_data from wagtail.blocks.migrations.utils because the block paths it
            # uses target blocks by their type names, so if there are two sibling blocks of the same type, there is no
            # way to target just one of them. In contrast to `ref.model_path`, this is taken into account by
            # `content_path`, which identifies StreamBlock children by UUID instead of their type, so we should use
            # this one instead. Unfortunately there is no easy way to quickly change a value with a given content path.
            # There is `StreamField.get_blockby_content_path()`, but this returns a `BoundBlock`, which does not
            # propagate changes to its value to the StreamField's value.
            field_name, *content_path_rest = content_path.split('.')
            assert field_name == source_field.name
            # Make sure we only update copies (pk is None for draft-only objects deserialized from revisions)
            assert from_object.pk is None or self.clone_visitor.is_copy(from_object)
            update_streamfield_block(from_object, field_name, content_path_rest, to_object, copy)
            return True

        if isinstance(source_field, ManyToOneRel):
            if not isinstance(from_object, ClusterableModel):
                # In this case, we will update the reference elsewhere using the clone structure. (I hope!)
                return False
            # For ClusterableModels (Pages, Organizations, etc.) owning cluster-related objects, we can't rely
            # on the clone structure to update references because copying these models uses special logic
            # (Wagtail's Page.copy() for pages, or cluster-related object handling for other ClusterableModels).
            # Additionally, Wagtail's reference index stores references from cluster-related child objects
            # at the parent level. For example, if an Indicator (child) has a reference in its description field,
            # Wagtail stores this in the reference index at the Organization (parent) level with a content path
            # like "indicators.123.description.". So we need to handle these references here by traversing into
            # the child objects.
            # `from_object` is the parent of an object that references
            # `ref.to_content_type.get_object_for_this_type(id=ref.to_object_id)`.
            # The referencing object is of type `source_field.related_model`.
            field_name, id, *content_path_rest = content_path.split('.')
            assert field_name == source_field.name
            assert field_name == source_field.related_name
            manager = getattr(from_object, field_name)
            assert isinstance(manager, Manager)
            # Create `from_object._cluster_related_objects`
            manager.get_object_list()  # type: ignore[attr-defined]
            referencing_object = manager.get(id=id)
            # Make sure we only update copies
            assert self.clone_visitor.is_copy(referencing_object)
            child_field_name, *child_content_path = content_path_rest
            child_field = referencing_object._meta.get_field(child_field_name)
            if isinstance(child_field, StreamField):
                update_streamfield_block(referencing_object, child_field_name, child_content_path, to_object, copy)
                assert field_name in from_object._cluster_related_objects
            elif isinstance(child_field, RichTextField):
                assert child_content_path == ['']
                update_rich_text_reference_in_field(
                    instance=referencing_object,
                    field_name=child_field_name,
                    old_referenced_object=to_object,
                    new_referenced_object=copy,
                )
            else:
                # Not sure if there are other cases, but I haven't accounted for any others...
                assert isinstance(child_field, (ForeignKey, GenericForeignKey))
                setattr(referencing_object, child_field_name, copy)
            return True

        if isinstance(source_field, ForeignKey):
            assert source_field.name == content_path
            # Foreign keys should have been already taken care of in a previous call to `self.update_foreign_keys()`
            assert getattr(from_object, source_field.name) is copy
            return False

        if isinstance(source_field, RichTextField):
            field_name, *content_path_rest = content_path.split('.')
            assert field_name == source_field.name
            assert content_path_rest == ['']
            # Make sure we only update copies (pk is None for draft-only objects deserialized from revisions)
            assert from_object.pk is None or self.clone_visitor.is_copy(from_object)
            update_rich_text_reference_in_field(
                instance=from_object,
                field_name=field_name,
                old_referenced_object=to_object,
                new_referenced_object=self.clone_visitor.get_copy(to_object),
            )
            return True

        raise TypeError("Unexpected source field type")

    def update_indexed_references(
            self,
            instance: Model,
            filter_reference: Callable[[ReferenceIndex], bool] | None = None,
    ) -> list[str]:
        update_fields = set()
        for ref in ReferenceIndex.get_references_for_object(instance):
            if filter_reference is not None and not filter_reference(ref):
                continue
            to_model = ref.to_content_type.model_class()
            try:
                to_object = ref.to_content_type.get_object_for_this_type(id=ref.to_object_id)
            except to_model.DoesNotExist:
                from_model = ref.content_type.model_class()
                from_object = from_model.objects.get(id=ref.object_id)
                from_original_pk = self.clone_visitor._get_original_pk(from_object)
                logger.warning(
                    f"Cannot update reference: {from_model.__name__} {ref.object_id} (copy of {from_original_pk}) "
                    f"references {to_model.__name__} {ref.to_object_id}, which does not exist. Keeping broken "
                    "reference in place."
                )
                continue
            updated = self.update_reference(
                from_object=instance,
                to_object=to_object,
                source_field=ref.source_field,
                content_path=ref.content_path,
            )
            if updated:
                update_fields.add(ref.source_field.name)
        return list(update_fields)

    def update_page_draft(self, page: Page) -> list[str]:
        updated_fields = []
        if page.latest_revision:
            assert isinstance(page.latest_revision, Revision)
            rev_obj = page.latest_revision.as_object()
            assert rev_obj.pk == page.pk
            # Update but don't save `rev_obj`. (Otherwise we'd overwrite published pages with drafts. We just want to
            # create a revision out of `rev_obj` and save that.
            # We set `skip_page_draft=True` to skip updating the latest revision of `rev_obj` because that would be an
            # infinite loop.
            updated = self.update_instance(rev_obj, save=False, skip_page_draft=True)
            if updated:
                new_rev = rev_obj.save_revision(changed=False)
                page.latest_revision = new_rev
                updated_fields.append('latest_revision')
        return updated_fields

    def visit(self, node: TreeNode) -> None:
        self.update_instance(node.instance)


def copy_root_pages(
    root_page: PlanRootPage | DocumentationRootPage, title_suffix: str | None = None,
) -> list[tuple[Page, Page]]:
    """
    Copy the given root page and all its translations.

    A root page can be, e.g., a plan root page or a documentation root page.

    A suffix can be appended to the title field of the root page using the argument `title_suffix` (defaults to `''`).
    If a suffix is appended, a space is put before it.

    Returns a list of (original, copy) tuples for the root page and each of its translations.
    """
    if title_suffix is None:
        title_suffix = ''

    if title_suffix:
        title_suffix = ' ' + title_suffix

    update_attrs = {
        'title': root_page.title + title_suffix,
        'slug': root_page.default_slug_for_copying(),
    }
    root_page_copy = root_page.copy(recursive=True, update_attrs=update_attrs)
    copies: list[tuple[Page, Page]] = [(root_page, root_page_copy)]
    new_translation_key = root_page_copy.translation_key
    assert root_page_copy.translation_key != root_page.translation_key
    # When copying the translations of `root_page`, reuse this translation key
    for page in root_page.get_translations():
        assert isinstance(page, (PlanRootPage, DocumentationRootPage))
        update_attrs = {
            'translation_key': new_translation_key,
            'title': page.title + title_suffix,
            'slug': page.default_slug_for_copying(),
        }
        translation_copy = page.copy(recursive=True, update_attrs=update_attrs)
        copies.append((page, translation_copy))
    return copies


def _copy_instance_revision(
    instance: RevisionMixin, clone_visitor: CloneVisitor, update_references_visitor: UpdateReferencesVisitor,
) -> None:
    try:
        rev_obj = instance.latest_revision.as_object()
    except Exception as exc:
        # Some non-ClusterableModel models with i18n fields that reference FKs
        # (e.g., default_language_field='plan__primary_language_lowercase') cannot be
        # deserialized from revision content because the FK isn't in the serialized data.
        # Clear the stale reference to the original's revision.
        model_name = type(instance).__name__
        logger.opt(exception=True).warning(
            f'Failed to deserialize revision for {model_name} pk={instance.pk}, skipping '
            f'({type(exc).__name__}: {exc})'
        )
        instance.latest_revision = None
        instance.save(update_fields=['latest_revision'])
        return
    # as_object() sets pk from the revision's content_object (the original), so fix it to the copy's pk
    rev_obj.pk = instance.pk
    if hasattr(rev_obj, 'uuid'):
        rev_obj.uuid = instance.uuid
    if hasattr(rev_obj, 'copy_of'):
        rev_obj.copy_of = instance.copy_of
    # Update but don't save `rev_obj`. (Otherwise we'd overwrite published instances with drafts. We just want to
    # create a revision out of `rev_obj` and save that.)
    update_references_visitor.update_instance(rev_obj, save=False)
    draft_attributes = getattr(rev_obj, 'draft_attributes', None)
    if draft_attributes:
        draft_attributes.replace_references(clone_visitor)
    new_rev = rev_obj.save_revision(changed=False)
    instance.latest_revision = new_rev
    instance.save(update_fields=['latest_revision'])


def copy_revisions(clone_visitor: CloneVisitor):
    update_references_visitor = UpdateReferencesVisitor(clone_visitor)
    for instance in clone_visitor.copies.values():
        if not isinstance(instance, RevisionMixin):
            continue
        if isinstance(instance, Page):
            continue  # Page revisions handled by UpdateReferencesVisitor.update_page_draft()
        if instance.latest_revision is None:
            continue
        _copy_instance_revision(instance, clone_visitor, update_references_visitor)


def copy_collection_with_contents(collection: Collection, clone_visitor: CloneVisitor):
    images_or_documents: chain[AbstractImage | AbstractDocument] = chain(
        AplansImage.objects.filter(collection_id=collection.pk),
        AplansDocument.objects.filter(collection_id=collection.pk),
    )
    clone(collection, {}, clone_visitor)
    for image_or_document in images_or_documents:
        clone(image_or_document, {}, clone_visitor)
        image_or_document.collection = collection
        file = image_or_document.file
        try:
            content_file = ContentFile(file.read(), name=file.name)
            filename = file.name.split('/')[-1]
            file.save(filename, content_file)
        except FileNotFoundError as e:
            logger.warning(f"Could not copy file of collection item {image_or_document}: {e}")
        image_or_document.save()


def _new_site_hostname(old_plan: Plan, new_plan_identifier: str) -> str:
    old_identifier = old_plan.identifier
    old_plan.identifier = new_plan_identifier
    new_site_hostname = old_plan.default_hostname()
    old_plan.identifier = old_identifier
    return new_site_hostname


def update_reference_index_immediately(f: Callable[P, R]) -> Callable[P, R]:
    """
    Force immediate update of Wagtail's reference index when saving model instances within a call to `f`.

    When a model instance is saved, Wagtail enqueues a task to update the reference index. By default, this task is
    executed when the current transaction is committed. This may cause problems if the code within the transaction not
    only saves some model instances but also relies on the reference index being kept up to date before the transaction
    ends.

    When this decorator is used on a function `f`, this behavior is changed during the call to `f` in such a way that
    the reference index is updated immediately when a model instance is saved.
    """
    @wraps(f)
    def wrapped(*args, **kwargs) -> R:
        original_task = wagtail.signal_handlers.update_reference_index_task  # type: ignore[attr-defined]
        tmp_task = dataclasses.replace(original_task, enqueue_on_commit=False)
        try:
            wagtail.signal_handlers.update_reference_index_task = tmp_task  # type: ignore[attr-defined]
            return f(*args, **kwargs)
        finally:
            wagtail.signal_handlers.update_reference_index_task = original_task  # type: ignore[attr-defined]

    return wrapped


def get_cluster_related_objects(instance: Model) -> Generator[tuple[str, Model]]:
    """
    Return objects that have a parental key to the given model instance.

    This is not recursive. More complex data models would probably need recursion, but for our current model, this
    should do.
    """
    if isinstance(instance, ClusterableModel):
        for child_relation in get_all_child_relations(instance):
            assert isinstance(child_relation.remote_field, ParentalKey)
            field_name = child_relation.get_accessor_name()
            manager = getattr(instance, field_name)
            for x in manager.get_object_list():
                yield field_name, x


def register_page_copies(clone_visitor: CloneVisitor, original_root: Page, root_copy: Page):
    """
    Register the pages in the tree rooted at `root_copy` as copies of those rooted at `original_root`.

    Also registers objects "owned" by the pages, i.e., objects with a parental key to a page.

    The two page trees must be isomorphic.
    """
    original_pages = original_root.get_descendants(inclusive=True).specific()
    page_copies = root_copy.get_descendants(inclusive=True).specific()
    for original_page, page_copy in zip(original_pages, page_copies, strict=True):
        assert type(original_page) is type(page_copy)
        clone_visitor.register_copy(original_page, page_copy)
        original_children = (obj for _, obj in get_cluster_related_objects(original_page))
        copy_children = (obj for _, obj in get_cluster_related_objects(page_copy))
        for original_child, child_copy in zip(original_children, copy_children, strict=True):
            clone_visitor.register_copy(original_child, child_copy)


def _validate_copy_plan_args(plan: Plan, new_plan_identifier: str, new_site_hostname: str, copy_indicators: bool) -> None:
    """
    Validate arguments for copy_plan before any mutations.

    Raises ValueError if validation fails.
    """
    if Plan.objects.filter(identifier=new_plan_identifier).exists():
        raise ValueError(f"A plan with identifier '{new_plan_identifier}' already exists")
    if Site.objects.filter(hostname=new_site_hostname).exists():
        raise ValueError(f"A site with hostname '{new_site_hostname}' already exists")

    if not copy_indicators:
        return

    plan_has_shared_indicator = (
        IndicatorLevel.objects.filter(indicator__in=plan.indicators.all())
        .values('indicator').annotate(num_plans=Count('plan')).filter(num_plans__gt=1)
    )
    if plan_has_shared_indicator:
        raise ValueError("Cannot copy indicators as the plan shares indicators with another plan")
    # We decided not to copy organizations and common indicators. So the unique constraint on `(common_id,
    # organization_id)` in `Indicator` prevents us from copying indicators that are instances of a common indicator.
    if plan.indicators.filter(common__isnull=False).exists():
        raise ValueError("Cannot copy indicators as some are instances of a common indicator")


def _clone_plan_objects(
    plan: Plan,
    clone_visitor: CloneVisitor,
    root_page_title_suffix: str | None,
    copy_indicators: bool,
) -> Plan:
    """
    Perform the actual cloning of all plan objects within a transaction.

    Returns the copy of the plan.
    """
    # Work on fresh `Plan` objects because `clone` changes its first argument. We just want to get stuff into the
    # visitor's copy cache (and the DB of course).
    root_collection = Plan.objects.get(pk=plan.pk).root_collection
    if root_collection:
        copy_collection_with_contents(root_collection, clone_visitor)
    clone(Plan.objects.get(pk=plan.pk).site, {}, clone_visitor)
    assert plan.site
    assert isinstance(plan.site.root_page.specific, PlanRootPage)
    root_page_copies = copy_root_pages(
        root_page=plan.site.root_page.specific,
        title_suffix=root_page_title_suffix,
    )
    for original_root, root_copy in root_page_copies:
        register_page_copies(clone_visitor, original_root, root_copy)
    root_page_copy = root_page_copies[0][1]
    plan_copy = Plan.objects.get(pk=plan.pk)
    # Hack to avoid site (and root page) initialization in Plan.save()  # noqa: FIX004
    plan_copy._site_created = True

    # Copy plan
    with ExitStack() as stack:
        # Disconnect signals to prevent creating related model instances when saving the plan
        stack.enter_context(temp_disconnect_signal(signals.post_save, create_notification_settings, Plan))
        stack.enter_context(temp_disconnect_signal(signals.post_save, create_plan_features_and_sync_group_permissions, Plan))
        stack.enter_context(temp_disconnect_signal(
            signals.post_save, create_site_general_content, Plan, 'create_site_general_content'
        ))
        # We leave the signal update_plan_domain_deploy_info enabled
        clone(plan_copy, PLAN_CLONE_STRUCTURE, clone_visitor)

    # Copy documentation page hierarchy
    for documentation_root_page in plan.documentation_root_pages.all():
        doc_page_copies = copy_root_pages(
            root_page=documentation_root_page,
            title_suffix=root_page_title_suffix,
        )
        for original_doc_root, doc_root_copy in doc_page_copies:
            register_page_copies(clone_visitor, original_doc_root, doc_root_copy)
        doc_root_page_copy = doc_page_copies[0][1]
        assert isinstance(doc_root_page_copy, DocumentationRootPage)
        doc_root_page_copy.plan = plan_copy
        doc_root_page_copy.save(update_fields=['plan'])

    # Attribute types use generic foreign keys, so we need to copy them ourselves
    plan_ct = ContentType.objects.get_for_model(Plan)
    category_type_ct = ContentType.objects.get_for_model(CategoryType)
    # Materialize attribute types in list because we'll update them in place
    attribute_types = list(AttributeType.objects.filter(
        (Q(scope_content_type=plan_ct) & Q(scope_id=plan.id))
        | (Q(scope_content_type=category_type_ct) & Q(scope_id__in=plan.category_types.all()))
    ))
    for at in attribute_types:
        clone(at, ATTRIBUTE_TYPE_CLONE_STRUCTURE, clone_visitor)

    # Update root page (`plan_copy.site` should now be the site copy)
    assert plan_copy.site
    plan_copy.site.root_page = root_page_copy
    plan_copy.site.save(update_fields=['root_page'])

    # Revisions have not been copied yet. (`Action.revisions` is not a reverse accessor, so we can't include action
    # revisions in the clone hierarchy.)
    # We decided that, when copying, we start with a clean slate revision-wise, except for the latest revision, which
    # may be the current, yet unpublished, draft.
    copy_revisions(clone_visitor)

    if copy_indicators:
        indicators = list(plan.indicators.all())
        for indicator in indicators:
            clone(indicator, INDICATOR_CLONE_STRUCTURE, clone_visitor)
        for dimension in Dimension.objects.filter(id__in=plan.dimensions.values_list('dimension_id')):
            clone(dimension, DIMENSION_CLONE_STRUCTURE, clone_visitor)
    else:
        indicators = []

    # Restore temporarily removed links
    clone_visitor.restore_removed_links()
    update_references(plan_copy, attribute_types, indicators, clone_visitor)

    return plan_copy


@update_reference_index_immediately
def copy_plan(
    plan: Plan,
    new_plan_identifier: str | None = None,
    new_plan_name: str | None = None,
    general_name_suffix: str | None = None,
    root_page_title_suffix: str | None = None,
    version_name: str | None = None,
    supersede_original_plan: bool = False,
    supersede_original_actions: bool = False,
    copy_indicators: bool = False,
) -> Plan:
    """
    Copy the given plan.

    Sets identifier and name of the copy of the plan to the given values, defaults to the result of calling
    `default_identifier_for_copying()` and `default_name_for_copying()` on the original.

    Adds the suffix given in `general_name_suffix` to the names of other models. (Defaults to no suffix.)

    Does what you expect for `root_page_title_suffix`.

    The plan version name of the copy can be specified with `version_name`.

    If `supersede_original_plan` is true, the copy will supersede the original plan; if
    `supersede_original_actions` is true, each action copy will supersede its original.

    If `copy_indicators` is true, all indicators and dimensions of `plan` will be copied. However, this requires the
    plan to have only indicators that are not shared with another plan, otherwise we abort.

    Returns the copy.
    """
    if new_plan_identifier is None:
        new_plan_identifier = plan.default_identifier_for_copying()
    if new_plan_name is None:
        new_plan_name = plan.default_name_for_copying()

    new_site_hostname = _new_site_hostname(plan, new_plan_identifier)
    _validate_copy_plan_args(plan, new_plan_identifier, new_site_hostname, copy_indicators)

    clone_visitor = CloneVisitor(
        site_hostname=new_site_hostname,
        plan_identifier=new_plan_identifier,
        plan_name=new_plan_name,
        copy_name_suffix=general_name_suffix,
        version_name=version_name,
        supersede_original_plan=supersede_original_plan,
        supersede_original_actions=supersede_original_actions,
    )

    with transaction.atomic():
        return _clone_plan_objects(plan, clone_visitor, root_page_title_suffix, copy_indicators)


def update_references(
    plan_copy: Plan,
    attribute_types: list[AttributeType],
    indicators: list[Indicator],
    clone_visitor: CloneVisitor,
):
    update_references_visitor = UpdateReferencesVisitor(clone_visitor)
    visit_tree(plan_copy, PLAN_CLONE_STRUCTURE, update_references_visitor)
    update_references_in_page_tree_with_translations(plan_copy.root_page, update_references_visitor)
    for page in plan_copy.documentation_root_pages.all():
        update_references_in_page_tree_with_translations(page, update_references_visitor)
    for at in attribute_types:
        visit_tree(at, ATTRIBUTE_TYPE_CLONE_STRUCTURE, update_references_visitor)
    update_references_in_indicators(indicators, clone_visitor)


def update_references_in_page_tree_with_translations(root_page: Page, update_references_visitor: UpdateReferencesVisitor):
    for translation in root_page.get_translations(inclusive=True):
        for page in translation.get_descendants(inclusive=True).specific():
            update_references_visitor.update_instance(page)


def update_references_in_indicators(indicators: list[Indicator], clone_visitor: CloneVisitor):
    """
    Update references in copied indicators.

    Since Indicator has a ParentalKey to Organization, references from indicators are stored in Wagtail's
    reference index at the Organization level, not the Indicator level. We need to process references at the
    parent Organization level to update the cluster-related indicator objects, but we don't want to modify or
    save the Organization instances themselves.
    """
    from orgs.models import Organization

    update_references_visitor = UpdateReferencesVisitor(clone_visitor)

    # Set up filter to only process references whose content path is `indicators.<n>.*`, where `<n>` is the PK of an
    # indicator we copied.
    indicator_pks = {i.pk for i in indicators}
    def filter_reference(ref: ReferenceIndex) -> bool:
        parts = ref.content_path.split('.', maxsplit=2)
        if len(parts) < 2:
            return False
        field, pk_str = parts[0], parts[1]
        if field != 'indicators' or not pk_str.isdigit():
            return False
        return int(pk_str) in indicator_pks

    # Collect all organizations that contain the copied indicators
    org_ids = set()
    for indicator in indicators:
        assert clone_visitor.is_copy(indicator)
        assert indicator.organization is not None
        org_ids.add(indicator.organization_id)  # type: ignore[attr-defined]

    # Process indexed references at the Organization level
    # This updates indicators in the org's _cluster_related_objects
    for org_id in org_ids:
        org = Organization.objects.get(pk=org_id)
        # Process indexed references (this modifies cluster children in memory)
        update_references_visitor.update_indexed_references(org, filter_reference)
        # Save only the modified cluster-related indicators, not the org itself
        for _, child in get_cluster_related_objects(org):
            if isinstance(child, Indicator) and clone_visitor.is_copy(child):
                child.save()

    # Also visit the indicator tree to handle foreign keys and other references
    # in indicators and their related objects (values, goals, dimensions, etc.)
    for indicator in indicators:
        visit_tree(indicator, INDICATOR_CLONE_STRUCTURE, update_references_visitor)


def visit_tree(root: Model, config: dict, visitor: AbstractVisitor) -> None:
    tree = ConfigurableRelationTree(root=root, structure=config)
    for node in RelationTreeIterator(tree=tree):
        visitor.visit(node)
