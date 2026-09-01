from __future__ import annotations

import json

import pytest

from actions.models.plan import Plan
from actions.tests.factories import ActionFactory, PlanFactory
from copying.export import (
    EXPORT_PLAN_STRUCTURE,
    build_export_plan_structure,
    build_media_manifest,
    collect_export_instances,
    serialize_plan,
)
from copying.tests.test_clone_structure_coverage import _check_coverage
from images.tests.factories import AplansImageFactory


class TestExportStructureCoverage:
    def test_default_export_structure_coverage(self):
        _check_coverage(Plan, EXPORT_PLAN_STRUCTURE, set())

    def test_export_structure_with_all_flags_coverage(self):
        structure = build_export_plan_structure(
            include_pledges=True,
            include_feedback=True,
            include_audit_logs=True,
        )
        _check_coverage(Plan, structure, set())


class TestExportStructureReclassification:
    def test_reports_are_included(self):
        assert EXPORT_PLAN_STRUCTURE['report_types'] == {'reports': {'action_snapshots': {}}}

    def test_plan_links_are_included(self):
        assert EXPORT_PLAN_STRUCTURE['links'] == {}

    def test_domains_stay_excluded(self):
        # Plan domains must stay out: hostname/base path are unique per plan.
        from copying.main import Excluded

        assert isinstance(EXPORT_PLAN_STRUCTURE['domains'], Excluded)

    def test_pledges_and_feedback_are_gated(self):
        from copying.main import Excluded

        default = build_export_plan_structure()
        default_pledges = default['pledges']
        assert isinstance(default_pledges, dict)
        assert isinstance(default['user_feedbacks'], Excluded)
        assert isinstance(default_pledges['commitments'], Excluded)

        opened = build_export_plan_structure(include_pledges=True, include_feedback=True)
        opened_pledges = opened['pledges']
        assert isinstance(opened_pledges, dict)
        assert opened['user_feedbacks'] == {}
        assert opened_pledges['commitments'] == {}


@pytest.mark.django_db
class TestTenantIsolation:
    def test_export_contains_only_the_target_plans_objects(self):
        plan_a = PlanFactory.create()
        plan_b = PlanFactory.create()
        action_a = ActionFactory.create(plan=plan_a)
        action_b = ActionFactory.create(plan=plan_b)

        records = json.loads(serialize_plan(plan_a))
        keys = {(r['model'], r['pk']) for r in records}

        assert ('actions.plan', plan_a.pk) in keys
        assert ('actions.action', action_a.pk) in keys

        # Nothing belonging to the other tenant may appear.
        assert ('actions.plan', plan_b.pk) not in keys
        assert ('actions.action', action_b.pk) not in keys

    def test_no_other_plan_rows_leak_for_any_model(self):
        plan_a = PlanFactory.create()
        plan_b = PlanFactory.create()
        ActionFactory.create(plan=plan_b)

        records = json.loads(serialize_plan(plan_a))
        exported_plan_pks = {r['pk'] for r in records if r['model'] == 'actions.plan'}
        assert exported_plan_pks == {plan_a.pk}


@pytest.mark.django_db
class TestSerializePlan:
    def test_output_is_valid_dumpdata_json(self):
        plan = PlanFactory.create()
        ActionFactory.create(plan=plan)

        records = json.loads(serialize_plan(plan))
        assert isinstance(records, list)
        assert all({'model', 'pk', 'fields'} <= record.keys() for record in records)
        assert any(r['model'] == 'actions.action' for r in records)

    def test_pages_and_site_are_exported(self, plan_with_pages):
        records = json.loads(serialize_plan(plan_with_pages))
        models = {r['model'] for r in records}
        # Multi-table inheritance: the base page row is always present.
        assert 'wagtailcore.page' in models
        assert 'wagtailcore.site' in models

    def test_no_indicators_flag_drops_indicators(self, plan_with_pages):
        from indicators.tests.factories import IndicatorFactory, IndicatorLevelFactory

        indicator = IndicatorFactory.create(organization=plan_with_pages.organization)
        IndicatorLevelFactory.create(plan=plan_with_pages, indicator=indicator)

        with_indicators = json.loads(serialize_plan(plan_with_pages, include_indicators=True))
        without_indicators = json.loads(serialize_plan(plan_with_pages, include_indicators=False))

        assert any(r['model'] == 'indicators.indicator' for r in with_indicators)
        assert not any(r['model'] == 'indicators.indicator' for r in without_indicators)


@pytest.mark.django_db
class TestMediaManifest:
    def test_manifest_lists_plan_collection_images(self, plan_with_pages):
        image = AplansImageFactory.create(collection=plan_with_pages.root_collection, title='exported')
        instances = collect_export_instances(plan_with_pages)
        manifest = build_media_manifest(instances)
        assert image.file.name in manifest['images']


@pytest.mark.django_db
class TestReferencedIndicatorClosure:
    def test_orphan_indicator_referenced_by_action_is_included(self):
        from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory

        plan = PlanFactory.create()
        action = ActionFactory.create(plan=plan)
        # An indicator with no IndicatorLevel belongs to no plan (orphan), but is referenced
        # by an action in this plan.
        orphan = IndicatorFactory.create()
        ActionIndicatorFactory.create(action=action, indicator=orphan)

        keys = {(r['model'], r['pk']) for r in json.loads(serialize_plan(plan))}
        assert ('indicators.indicator', orphan.pk) in keys

    def test_indicator_owned_by_another_plan_is_not_included(self):
        from indicators.tests.factories import ActionIndicatorFactory, IndicatorFactory, IndicatorLevelFactory

        plan_a = PlanFactory.create()
        plan_b = PlanFactory.create()
        action_a = ActionFactory.create(plan=plan_a)
        indicator_b = IndicatorFactory.create()
        IndicatorLevelFactory.create(plan=plan_b, indicator=indicator_b)  # now owned by plan B
        ActionIndicatorFactory.create(action=action_a, indicator=indicator_b)

        keys = {(r['model'], r['pk']) for r in json.loads(serialize_plan(plan_a))}
        # Isolation: plan B's indicator must not ride along even though plan A's action references it.
        assert ('indicators.indicator', indicator_b.pk) not in keys


@pytest.mark.django_db
class TestReferencedMedia:
    def test_image_outside_plan_collection_is_included_via_reference(self, plan_with_pages):
        from wagtail.models import Collection

        from pages.tests.factories import StaticPageFactory

        # An image that lives outside the plan's own collection, referenced by a page header.
        other_collection = Collection.get_first_root_node()
        image = AplansImageFactory.create(collection=other_collection, title='header')
        StaticPageFactory.create(parent=plan_with_pages.root_page, header_image=image)

        keys = {(r['model'], r['pk']) for r in json.loads(serialize_plan(plan_with_pages))}
        assert ('images.aplansimage', image.pk) in keys


@pytest.mark.django_db
class TestSharedObjectClosure:
    def test_org_ancestors_included_with_flag(self):
        from orgs.tests.factories import OrganizationFactory

        parent_org = OrganizationFactory.create()
        child_org = OrganizationFactory.create(parent=parent_org)
        plan = PlanFactory.create(organization=child_org)

        with_shared = {(r['model'], r['pk']) for r in json.loads(serialize_plan(plan, include_referenced_shared_objects=True))}
        # The referenced org and its ancestor are both pulled in.
        assert ('orgs.organization', child_org.pk) in with_shared
        assert ('orgs.organization', parent_org.pk) in with_shared

    def test_shared_objects_excluded_by_default(self):
        from orgs.tests.factories import OrganizationFactory

        org = OrganizationFactory.create()
        plan = PlanFactory.create(organization=org)

        default = {(r['model'], r['pk']) for r in json.loads(serialize_plan(plan))}
        assert ('orgs.organization', org.pk) not in default

    def test_shared_org_ancestor_is_visited_once(self):
        from orgs.tests.factories import OrganizationFactory

        # Two referenced orgs share a parent; the parent must be pulled in exactly once.
        parent = OrganizationFactory.create()
        child_a = OrganizationFactory.create(parent=parent)
        child_b = OrganizationFactory.create(parent=parent)
        plan = PlanFactory.create(organization=child_a)
        ActionFactory.create(plan=plan, primary_org=child_b)

        records = json.loads(serialize_plan(plan, include_referenced_shared_objects=True))
        org_pks = [r['pk'] for r in records if r['model'] == 'orgs.organization']
        assert org_pks.count(parent.pk) == 1
        assert {child_a.pk, child_b.pk} <= set(org_pks)


class TestExportStructureHelpers:
    def test_set_rejects_descending_into_excluded_relation(self):
        from copying.export import _deepcopy_structure, _set
        from copying.main import PLAN_CLONE_STRUCTURE

        structure = _deepcopy_structure(PLAN_CLONE_STRUCTURE)
        # `domains` is EXCLUDED, so it cannot be descended into.
        with pytest.raises(TypeError):
            _set(structure, ['domains', 'anything'], {})

    def test_set_rejects_unknown_relation(self):
        from copying.export import _deepcopy_structure, _set
        from copying.main import PLAN_CLONE_STRUCTURE

        structure = _deepcopy_structure(PLAN_CLONE_STRUCTURE)
        with pytest.raises(ValueError, match='is not a key'):
            _set(structure, ['this_relation_does_not_exist'], {})


@pytest.mark.django_db
class TestCollectorEdgeCases:
    def test_collection_and_media_collectors_handle_missing_root_collection(self):
        from copying.export import iter_plan_collection_instances, iter_plan_media_instances

        plan = PlanFactory.create()
        plan.root_collection = None
        assert list(iter_plan_collection_instances(plan)) == []
        assert list(iter_plan_media_instances(plan)) == []

    def test_relational_reference_targets_includes_generic_fk(self):
        from actions.tests.factories import AttributeTypeFactory
        from copying.export import _iter_relational_reference_targets

        plan = PlanFactory.create()
        # AttributeType.scope is a generic foreign key; here it points at the plan.
        attribute_type = AttributeTypeFactory.create(scope=plan)
        assert plan in list(_iter_relational_reference_targets(attribute_type))

    def test_documentation_root_page_is_exported(self, plan_with_pages):
        from wagtail.models import Page

        from copying.export import iter_plan_page_instances
        from documentation.models import DocumentationRootPage

        global_root = Page.get_first_root_node()
        assert global_root is not None
        doc_root = DocumentationRootPage(title='Docs', plan=plan_with_pages, slug='docs-export')
        global_root.add_child(instance=doc_root)

        page_pks = {page.pk for page in iter_plan_page_instances(plan_with_pages)}
        assert doc_root.pk in page_pks


@pytest.mark.django_db
class TestReferencedDimensionClosure:
    def test_orphan_indicator_pulls_in_its_dataset_schema_and_dimensions(self):
        from datasets.tests.factories import DatasetSchemaFactory
        from indicators.tests.factories import (
            ActionIndicatorFactory,
            DimensionFactory,
            IndicatorDimensionFactory,
            IndicatorFactory,
        )

        plan = PlanFactory.create()
        action = ActionFactory.create(plan=plan)
        schema = DatasetSchemaFactory.create()
        orphan = IndicatorFactory.create(dataset_schema=schema)
        dimension = DimensionFactory.create()  # orphan dimension, not attached to any plan
        IndicatorDimensionFactory.create(indicator=orphan, dimension=dimension)
        ActionIndicatorFactory.create(action=action, indicator=orphan)

        records = json.loads(serialize_plan(plan))
        keys = {(r['model'], r['pk']) for r in records}
        assert ('indicators.indicator', orphan.pk) in keys
        # Closing over the referenced indicator drags in the dimension it uses ...
        assert ('indicators.dimension', dimension.pk) in keys
        # ... and its dataset schema.
        assert any(r['model'].endswith('datasetschema') and r['pk'] == schema.pk for r in records)


@pytest.mark.django_db
class TestMediaViaReferenceIndex:
    def test_image_embedded_in_rich_text_is_included(self, plan_with_pages):
        from wagtail.models import Collection
        from wagtail.models.reference_index import ReferenceIndex

        action = ActionFactory.create(plan=plan_with_pages)
        image = AplansImageFactory.create(collection=Collection.get_first_root_node(), title='embedded')
        # An image embedded in rich text (tracked only by the ReferenceIndex, not a plain FK),
        # living outside the plan's own collection.
        action.description = f'<p data-block-key="k"><embed embedtype="image" format="fullwidth" id="{image.pk}" alt="x"/></p>'
        action.save()
        ReferenceIndex.create_or_update_for_object(action)

        keys = {(r['model'], r['pk']) for r in json.loads(serialize_plan(plan_with_pages))}
        assert ('images.aplansimage', image.pk) in keys


@pytest.mark.django_db
class TestReferencedPersonsManifest:
    def test_manifest_yields_referenced_contact_persons(self, plan_with_pages):
        from actions.tests.factories import ActionContactFactory
        from people.tests.factories import PersonFactory

        # The same person contacts two actions: the person-reference walk must yield them once
        # (exercises both the yield and the already-seen dedup branch).
        person = PersonFactory.create()
        action_a = ActionFactory.create(plan=plan_with_pages)
        action_b = ActionFactory.create(plan=plan_with_pages)
        ActionContactFactory.create(action=action_a, person=person)
        ActionContactFactory.create(action=action_b, person=person)

        instances = collect_export_instances(plan_with_pages)
        manifest = build_media_manifest(instances)
        assert set(manifest) == {'images', 'documents', 'avatars'}


@pytest.mark.django_db
class TestExportPlanCommand:
    def test_command_writes_json_and_media_manifest(self, plan_with_pages, tmp_path):
        from django.core.management import call_command

        ActionFactory.create(plan=plan_with_pages)
        output = tmp_path / 'plan.json'
        manifest = tmp_path / 'media.json'
        call_command(
            'export_plan',
            plan_with_pages.identifier,
            output=str(output),
            media_manifest=str(manifest),
        )
        records = json.loads(output.read_text())
        assert any(r['model'] == 'actions.plan' for r in records)
        assert set(json.loads(manifest.read_text())) == {'images', 'documents', 'avatars'}

    def test_command_errors_on_unknown_plan(self):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        with pytest.raises(CommandError):
            call_command('export_plan', 'no-such-plan-identifier')
