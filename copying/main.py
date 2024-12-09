from __future__ import annotations

from collections.abc import Generator, Iterable
from contextlib import ExitStack
from copy import copy as shallow_copy
from functools import singledispatchmethod
from typing import Any
from uuid import uuid4

from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db.models import Field, Model, Q, signals
from wagtail.fields import StreamField
from wagtail.models import Page, Revision, Site
from wagtail.models.media import Collection
from wagtail.models.reference_index import ReferenceIndex

from loguru import logger
from relations_iterator import AbstractVisitor, ConfigurableRelationTree, RelationTreeIterator, TreeNode, clone  # type: ignore

from actions.models.action import Action
from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryType
from actions.models.plan import Plan
from actions.signals import create_notification_settings, create_plan_features
from content.apps import create_site_general_content
from copying.utils import get_foreign_keys, get_generic_foreign_keys, temp_disconnect_signal, update_streamfield_block
from documentation.models import DocumentationRootPage
from pages.models import PlanRootPage

type CloneStructure = dict[str, CloneStructure]

# TODO: Models from other apps: budget, feedback, etc.
PLAN_CLONE_STRUCTURE: CloneStructure = {
    'action_decision_levels': {},
    'action_dependency_roles': {},
    'action_impacts': {},
    'action_implementation_phases': {},
    'action_schedules': {},
    'action_statuses': {},
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
        'categories': {},
        'levels': {},
    },
    'clients': {},
    # 'domains': {},  # deliberately don't copy domains because hostname + base path should be unique
    'features': {},
    'general_admins_ordered': {},
    'general_content': {},
    'impact_groups': {},
    'indicator_levels': {},  # We don't copy the indicators themselves
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
        self.removed_links = {}
        self.supersede_original_plan = supersede_original_plan
        self.supersede_original_actions = supersede_original_actions

    def get_copy[M: Model](self, instance: M) -> M:
        """Get the copy that has been created for the given instance."""
        copy = self.copies[(type(instance), instance.pk)]
        assert type(copy) is type(instance)
        assert isinstance(copy, type(instance))  # implied by previous line, but apparently mypy doesn't figure this out
        return copy

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
        key = (node.model_class, original_instance.pk)
        assert key not in self.copies
        self.copies[key] = node.instance
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

    def update_instance(self, instance: Model, save: bool = True):
        """Update all references from `instance` to objects that have been copied to point to the copies."""
        logger.trace(f"Update references of {type(instance).__name__} {instance.pk}: {instance}")
        update_fields = []
        update_fields += self.update_foreign_keys(instance)
        if isinstance(instance, Page):
            update_fields += self.update_streamfield_references(instance)
        # Save changes
        if update_fields and save:
            instance.save(update_fields=update_fields)
            logger.info(
                f"Updated references in {len(update_fields)} fields of "
                f"{type(instance).__name__} {instance.pk}: {instance}"
            )

    def _get_references(
        self, instance: Model, exclude_fields: Iterable[str] | None = None
    ) -> Generator[Field | GenericForeignKey]:
        if exclude_fields is None:
            exclude_fields = []
        for fk in get_foreign_keys(instance):
            if fk.name not in exclude_fields:
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

    def update_foreign_keys(self, instance: Model) -> list[str]:
        update_fields = []
        for fk in self.get_references(instance):
            assert hasattr(fk, 'name')
            related_object = getattr(instance, fk.name)
            if related_object:
                try:
                    copy = self.clone_visitor.get_copy(related_object)
                except KeyError:
                    logger.trace(
                        f"Could not find copy for {type(related_object).__name__} {related_object.pk}: "
                        f"{related_object}"
                    )
                    continue
                logger.trace(f"Set foreign key '{fk.name}' of {type(instance).__name__} {instance.pk} to: {copy}")
                setattr(instance, fk.name, copy)
                if isinstance(fk, GenericForeignKey):
                    # Technically we'd also need to update fk.ct_field, but content types don't change by copying
                    update_fields.append(fk.fk_field)
                else:
                    update_fields.append(fk.name)
        return update_fields

    def update_streamfield_references(self, page: Page) -> list[str]:
        update_fields = set()
        for ref in ReferenceIndex.get_references_for_object(page):
            referenced_object = ref.to_content_type.get_object_for_this_type(id=ref.to_object_id)
            try:
                copy = self.clone_visitor.get_copy(referenced_object)
            except KeyError:
                continue
            if not isinstance(ref.source_field, StreamField):
                continue

            # We can't use apply_changes_to_raw_data from wagtail.blocks.migrations.utils because the block paths it
            # uses target blocks by their type names, so if there are two sibling blocks of the same type, there is no
            # way to target just one of them. In contrast to `ref.model_path`, this is taken into account by
            # `ref.content_path`, which identifies StreamBlock children by UUID instead of their type, so we should use
            # this one instead. Unfortunately there is no easy way to quickly change a value with a given content path.
            # There is `StreamField.get_blockby_content_path()`, but this returns a `BoundBlock`, which does not
            # propagate changes to its value to the StreamField's value.
            field_name, *content_path = ref.content_path.split('.')
            update_streamfield_block(page, field_name, content_path, copy.pk)
            update_fields.add(field_name)
        return list(update_fields)

    def visit(self, node: TreeNode) -> None:
        self.update_instance(node.instance)


def copy_root_pages(root_page: PlanRootPage | DocumentationRootPage, title_suffix=None) -> Page:
    """
    Copy the given root page and all its translations.

    A root page can be, e.g., a plan root page or a documentation root page.

    A suffix can be appended to the title field of the root page using the argument `title_suffix` (defaults to `''`).
    If a suffix is appended, a space is put before it.

    Returns the copy of `root_page`.
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
    new_translation_key = root_page_copy.translation_key
    assert root_page_copy.translation_key != root_page.translation_key
    # When copying the translations of `root_page`, reuse this translation key
    update_attrs['translation_key'] = new_translation_key
    for page in root_page.get_translations():
        assert isinstance(page, PlanRootPage)
        update_attrs = {
            'translation_key': new_translation_key,
            'title': page.title + title_suffix,
            'slug': page.default_slug_for_copying(),
        }
        page.copy(recursive=True, update_attrs=update_attrs)
    return root_page_copy


def copy_action_drafts(plan_copy: Plan, clone_visitor: CloneVisitor):
    update_references_visitor = UpdateReferencesVisitor(clone_visitor)
    for action in plan_copy.actions.all():
        if action.latest_revision:
            assert isinstance(action.latest_revision, Revision)
            rev_obj = action.latest_revision.as_object()
            # The PK of `rev_obj` is that of the original from which `action` was copied
            rev_obj.pk = action.pk
            rev_obj.uuid = action.uuid
            # Update but don't save `rev_obj`. (Otherwise we'd overwrite published actions with drafts. We just want to
            # create a revision out of `rev_obj` and save that.
            update_references_visitor.update_instance(rev_obj, save=False)
            new_rev = rev_obj.save_revision()
            action.latest_revision = new_rev
            action.save(update_fields=['latest_revision'])


def _new_site_hostname(old_plan: Plan, new_plan_identifier: str) -> str:
    old_identifier = old_plan.identifier
    old_plan.identifier = new_plan_identifier
    new_site_hostname = old_plan.default_hostname()
    old_plan.identifier = old_identifier
    return new_site_hostname


def copy_plan(
    plan: Plan,
    new_plan_identifier: str | None = None,
    new_plan_name: str | None = None,
    general_name_suffix: str | None = None,
    root_page_title_suffix: str | None = None,
    version_name: str | None = None,
    supersede_original_plan: bool = False,
    supersede_original_actions: bool = False,
):
    """
    Copy the given plan.

    Sets identifier and name of the copy of the plan to the given values, defaults to the result of calling
    `default_identifier_for_copying()` and `default_name_for_copying()` on the original.

    Adds the suffix given in `general_name_suffix` to the names of other models. (Defaults to no suffix.)

    Does what you expect for `root_page_title_suffix`.

    The plan version name of the copy can be specified with `version_name`.

    If `supersede_original_plan` is true, the copy will supersede the original plan; if
    `supersede_original_actions` is true, each action copy will supersede its original.
    """
    if new_plan_identifier is None:
        new_plan_identifier = plan.default_identifier_for_copying()
    if new_plan_name is None:
        new_plan_name = plan.default_name_for_copying()

    clone_visitor = CloneVisitor(
        site_hostname=_new_site_hostname(plan, new_plan_identifier),
        plan_identifier=new_plan_identifier,
        plan_name=new_plan_name,
        copy_name_suffix=general_name_suffix,
        version_name=version_name,
        supersede_original_plan=supersede_original_plan,
        supersede_original_actions=supersede_original_actions,
    )
    # A couple of hacks to avoid things breaking when creating a copy of the plan.
    # Work on fresh `Plan` objects because `clone` changes its first argument. We just want to get stuff into the
    # visitor's copy cache (and the DB of course).
    clone(Plan.objects.get(pk=plan.pk).root_collection, {}, clone_visitor)
    clone(Plan.objects.get(pk=plan.pk).site, {}, clone_visitor)
    assert plan.site
    assert isinstance(plan.site.root_page.specific, PlanRootPage)
    root_page_copy = copy_root_pages(
        root_page=plan.site.root_page.specific,
        title_suffix=root_page_title_suffix,
    )
    plan_copy = Plan.objects.get(pk=plan.pk)

    # Copy plan
    with ExitStack() as stack:
        # Disconnect signals to prevent creating related model instances when saving the plan
        stack.enter_context(temp_disconnect_signal(signals.post_save, create_notification_settings, Plan))
        stack.enter_context(temp_disconnect_signal(signals.post_save, create_plan_features, Plan))
        stack.enter_context(temp_disconnect_signal(
            signals.post_save, create_site_general_content, Plan, 'create_site_general_content'
        ))
        # We leave the signal update_plan_domain_deploy_info enabled
        clone(plan_copy, PLAN_CLONE_STRUCTURE, clone_visitor)

    # Copy documentation page hierarchy
    for documentation_root_page in plan.documentation_root_pages.all():
        root_page = copy_root_pages(
            root_page=documentation_root_page,
            title_suffix=root_page_title_suffix,
        )
        assert isinstance(root_page, DocumentationRootPage)
        root_page.plan = plan_copy
        root_page.save(update_fields=['plan'])

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

    # Action revisions have not been copied yet. (`Action.revisions` is not a reverse accessor, so we can't include
    # revisions in the clone hierarchy.)
    # We decided that, when copying an action, we start with a clean slate revision-wise, except for the latest
    # revision, which may be the current, yet unpublished, draft.
    copy_action_drafts(plan_copy, clone_visitor)

    # Restore temporarily removed links
    clone_visitor.restore_removed_links()
    update_references(plan_copy, attribute_types, clone_visitor)


def update_references(plan_copy: Plan, attribute_types: list[AttributeType], clone_visitor: CloneVisitor):
    update_references_visitor = UpdateReferencesVisitor(clone_visitor)
    visit_tree(plan_copy, PLAN_CLONE_STRUCTURE, update_references_visitor)
    update_references_in_page_tree_with_translations(plan_copy.root_page, update_references_visitor)
    for page in plan_copy.documentation_root_pages.all():
        update_references_in_page_tree_with_translations(page, update_references_visitor)
    for at in attribute_types:
        visit_tree(at, ATTRIBUTE_TYPE_CLONE_STRUCTURE, update_references_visitor)


def update_references_in_page_tree_with_translations(root_page: Page, update_references_visitor: UpdateReferencesVisitor):
    for translation in root_page.get_translations(inclusive=True):
        for page in translation.get_descendants(inclusive=True).specific():
            update_references_visitor.update_instance(page)


def visit_tree(root: Model, config: dict, visitor: AbstractVisitor) -> None:
    tree = ConfigurableRelationTree(root=root, structure=config)
    for node in RelationTreeIterator(tree=tree):
        visitor.visit(node)
