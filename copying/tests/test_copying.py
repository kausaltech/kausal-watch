from __future__ import annotations

from django.contrib.contenttypes.models import ContentType
from wagtail.models import Page, Revision
from wagtail.rich_text import RichText

import pytest

from actions.models.action import Action
from actions.models.attributes import AttributeType
from actions.models.category import CategoryType
from actions.models.plan import Plan
from actions.tests.factories import (
    ActionContactFactory,
    ActionStatusFactory,
    ActionTaskFactory,
    AttributeChoiceWithTextFactory,
    AttributeRichTextFactory,
    AttributeTypeChoiceOptionFactory,
    AttributeTypeFactory,
    CategoryTypeFactory,
    PlanFactory,
    WorkflowFactory,
)
from documentation.models import DocumentationRootPage
from django.db import transaction
from wagtail.models.reference_index import ReferenceIndex

from copying.main import (
    CloneVisitor,
    UpdateReferencesVisitor,
    _clone_plan_objects,
    _new_site_hostname,
    _update_reference_index_immediately_ctx,
    _validate_copy_plan_args,
    copy_plan,
)
from documents.models import AplansDocument
from documents.tests.factories import AplansDocumentFactory
from images.models import AplansImage
from images.tests.factories import AplansImageFactory
from indicators.models.indicator import Indicator
from indicators.tests.factories import (
    ActionIndicatorFactory,
    DimensionCategoryFactory,
    IndicatorFactory,
    IndicatorGoalFactory,
    IndicatorLevelFactory,
    IndicatorValueFactory,
    RelatedIndicatorFactory,
)
from pages.models import StaticPage
from pages.tests.factories import CategoryTypePageLevelLayoutFactory
from reports.tests.factories import ReportTypeFactory

pytestmark = pytest.mark.django_db


class TestValidateCopyPlanArgs:
    def test_rejects_duplicate_plan_identifier(self, plan):
        new_site_hostname = _new_site_hostname(plan, 'new-identifier')
        with pytest.raises(ValueError, match="already exists"):
            _validate_copy_plan_args(plan, plan.identifier, new_site_hostname, copy_indicators=False)

    def test_rejects_duplicate_site_hostname(self, plan_with_pages):
        assert plan_with_pages.site is not None
        existing_hostname = plan_with_pages.site.hostname
        with pytest.raises(ValueError, match="already exists"):
            _validate_copy_plan_args(plan_with_pages, 'unique-identifier', existing_hostname, copy_indicators=False)

    def test_passes_with_valid_args(self, plan):
        new_identifier = 'brand-new-plan'
        new_site_hostname = _new_site_hostname(plan, new_identifier)
        # Should not raise
        _validate_copy_plan_args(plan, new_identifier, new_site_hostname, copy_indicators=False)

    def test_rejects_shared_indicators(self, plan, indicator):
        another_plan = PlanFactory.create()
        IndicatorLevelFactory.create(plan=another_plan, indicator=indicator)
        new_identifier = 'new-plan'
        new_site_hostname = _new_site_hostname(plan, new_identifier)
        with pytest.raises(ValueError, match='shares indicators with another plan'):
            _validate_copy_plan_args(plan, new_identifier, new_site_hostname, copy_indicators=True)

    def test_rejects_common_indicator_instances(self, plan, indicator):
        assert indicator.common is not None
        new_identifier = 'new-plan'
        new_site_hostname = _new_site_hostname(plan, new_identifier)
        with pytest.raises(ValueError, match='some are instances of a common indicator'):
            _validate_copy_plan_args(plan, new_identifier, new_site_hostname, copy_indicators=True)

    @pytest.mark.parametrize('indicator__common', [None])
    def test_passes_with_copy_indicators(self, plan, indicator):
        new_identifier = 'new-plan'
        new_site_hostname = _new_site_hostname(plan, new_identifier)
        # Should not raise when indicators are not shared and have no common indicator
        _validate_copy_plan_args(plan, new_identifier, new_site_hostname, copy_indicators=True)


def get_page_copy(page, plan_copy):
    page_copy = plan_copy.root_page.get_children().get(url_path=page.url_path).specific
    assert type(page_copy) is type(page)
    return page_copy


def html_with_references(instances):
    """Return HTML with references as Wagtail would produce it in a rich-text field."""
    html = '<p data-block-key="foo">'
    for instance in instances:
        if isinstance(instance, AplansDocument):
            html += f'<a linktype="document" id="{instance.pk}">{instance.title}</a>'
        elif isinstance(instance, AplansImage):
            html += f'<embed embedtype="image" format="fullwidth-zoomable" id="{instance.pk}" alt="{instance.title}"/>'
        elif isinstance(instance, Indicator):
            html += f'<a linktype="indicator" id="{instance.id}" uuid="{instance.uuid}">{instance.name}</a>'
        else:
            raise TypeError("Unexpected type for referenced instance")
    html += '</p>'
    return html


def test_publish_copied_action_does_not_steal_contact_persons(plan_with_pages, action, user):
    ActionContactFactory.create(action=action)
    plan = plan_with_pages
    plan.features.moderation_workflow = WorkflowFactory.create()
    plan.features.save(update_fields=['moderation_workflow'])
    action.save_revision(user=user)
    plan_copy = copy_plan(plan)
    assert action == plan.actions.first()
    action_copy = plan_copy.actions.first()
    assert action_copy
    assert isinstance(action_copy.latest_revision, Revision)
    action_copy.latest_revision.publish()
    assert action.contact_persons.exists()


def test_category_type_copy_references_copied_plan(plan_with_pages, category_type):
    assert plan_with_pages.category_types.get() == category_type
    plan_copy = copy_plan(plan_with_pages)
    category_type_copy = plan_copy.category_types.get()
    assert category_type_copy.plan == plan_copy


def test_copying_does_not_create_action_draft(plan_with_pages, action):
    assert not action.latest_revision
    copy_plan(plan_with_pages)
    action_copy = plan_with_pages.actions.get()
    assert not action_copy.latest_revision


def test_copying_creates_page_draft_without_changes(plan_with_pages, category_type_page):
    # We use Wagtail's copy_page to copy pages. This creates a new revision for each page. (This is in contrast to,
    # e.g., actions, where copying the plan does not create a new revision.) The new revision for the pages created by
    # copying should, however, not contain any changes.
    assert not category_type_page.latest_revision
    plan_copy = copy_plan(plan_with_pages)
    page_copy = get_page_copy(category_type_page, plan_copy)
    assert page_copy.latest_revision
    assert not page_copy.has_unpublished_changes


@pytest.mark.parametrize('category_type__synchronize_with_pages', [True])
def test_succeed_when_category_type_pages_are_synchronized(plan_with_pages, category_type, category, category_level):
    # The specified fixtures are necessary to prevent a regression that would raise a ValidationError when references
    # are updated in a draft of a category page when page synchronization is active and there are category levels
    copy_plan(plan_with_pages)


def test_update_references_in_page(plan_with_pages, category_type_page, attribute_type):
    CategoryTypePageLevelLayoutFactory.create(
        page=category_type_page,
        layout_main_top__0__attribute__attribute_type=attribute_type,
        # TODO: Also test updating of level at some point?
        level=None,
    )
    plan_copy = copy_plan(plan_with_pages)
    category_type_copy = plan_copy.category_types.get()
    page_copy = get_page_copy(category_type_page, plan_copy)
    layout_copy = page_copy.level_layouts.get()
    block_copy_attribute_type = layout_copy.layout_main_top[0].value['attribute_type']
    assert block_copy_attribute_type.scope == category_type_copy


def test_update_references_in_page_draft(plan_with_pages, category_type_page, attribute_type):
    # Create CategoryTypePageLevelLayout in draft
    layout = CategoryTypePageLevelLayoutFactory.build(
        page=category_type_page,
        layout_main_top__0__attribute__attribute_type=attribute_type,
        # TODO: Also test updating of level at some point?
        level=None,
    )
    category_type_page.level_layouts.add(layout)
    category_type_page.save_revision()
    plan_copy = copy_plan(plan_with_pages)
    category_type_copy = plan_copy.category_types.get()
    page_copy = get_page_copy(category_type_page, plan_copy)
    draft_copy = page_copy.latest_revision.as_object()
    layout_copy = draft_copy.level_layouts.get()
    block_copy_attribute_type = layout_copy.layout_main_top[0].value['attribute_type']
    assert block_copy_attribute_type.scope == category_type_copy


def test_plan_copy_has_new_collection(plan_with_pages):
    plan_copy = copy_plan(plan_with_pages)
    assert plan_copy.root_collection != plan_with_pages.root_collection


def test_image_copy_in_collection_copy(plan_with_pages):
    image = AplansImageFactory.create(collection=plan_with_pages.root_collection, title='image')
    plan_copy = copy_plan(plan_with_pages)
    image_copy = AplansImage.objects.get(collection=plan_copy.root_collection, title=image.title)
    assert image_copy.collection == plan_copy.root_collection


def test_document_copy_in_collection_copy(plan_with_pages):
    doc = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc')
    plan_copy = copy_plan(plan_with_pages)
    doc_copy = AplansDocument.objects.get(collection=plan_copy.root_collection, title=doc.title)
    assert doc_copy.collection == plan_copy.root_collection


def test_rich_text_field_references(plan_with_pages, action):
    doc1 = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc1')
    doc2 = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc2')
    image1 = AplansImageFactory.create(collection=plan_with_pages.root_collection, title='image1')
    image2 = AplansImageFactory.create(collection=plan_with_pages.root_collection, title='image2')
    action.description = html_with_references([doc1, doc2, image1, image2])
    action.save(update_fields=['description'])
    plan_copy = copy_plan(plan_with_pages)
    doc1_copy = AplansDocument.objects.get(collection=plan_copy.root_collection, title=doc1.title)
    doc2_copy = AplansDocument.objects.get(collection=plan_copy.root_collection, title=doc2.title)
    image1_copy = AplansImage.objects.get(collection=plan_copy.root_collection, title=image1.title)
    image2_copy = AplansImage.objects.get(collection=plan_copy.root_collection, title=image2.title)
    action_copy = plan_copy.actions.get()
    assert action_copy.description == html_with_references([doc1_copy, doc2_copy, image1_copy, image2_copy])


def test_rich_text_block_references(plan_with_pages, static_page):
    image = AplansImageFactory.create(collection=plan_with_pages.root_collection, title='image')
    static_page.body = [
        ('paragraph', RichText(html_with_references([image]))),
    ]
    static_page.save()
    plan_copy = copy_plan(plan_with_pages)
    image_copy = AplansImage.objects.get(collection=plan_copy.root_collection, title=image.title)
    page_copy = plan_copy.root_page.get_children().type(StaticPage).get().specific
    assert isinstance(page_copy, StaticPage)
    assert page_copy.body is not None
    assert page_copy.body[0].value.source == html_with_references([image_copy])


def test_indicators_are_shared_when_copy_indicators_is_false(plan_with_pages, indicator):
    # Do not copy indicators but share them between the original plan and the plan copy
    assert Indicator.objects.get() == indicator
    assert plan_with_pages.indicators.get() == indicator
    assert indicator.plans.count() == 1
    plan_copy = copy_plan(plan_with_pages, copy_indicators=False)
    assert indicator.plans.count() == 2
    # While we're at it, make sure no indicators are added or removed
    assert Indicator.objects.get() == indicator
    assert plan_with_pages.indicators.get() == indicator
    assert plan_copy.indicators.get() == indicator


@pytest.mark.parametrize('indicator__common', [None])
def test_copy_indicator(  # noqa: PLR0915
    plan_with_pages, action, indicator, category, plan_dimension, indicator_dimension, person,
):
    # Do not share indicators between the original plan and the plan copy but copy them from the original plan to the
    # plan copy
    assert plan_with_pages.indicators.get() == indicator
    indicator.contact_persons_unordered.add(person)
    # Create dimension categories for the test
    dimension = plan_dimension.dimension
    dimension_category1 = DimensionCategoryFactory.create(dimension=dimension)
    dimension_category2 = DimensionCategoryFactory.create(dimension=dimension)
    value = IndicatorValueFactory.create(indicator=indicator, categories=[dimension_category1, dimension_category2])
    goal = IndicatorGoalFactory.create(indicator=indicator)
    action_indicator = ActionIndicatorFactory.create(action=action, indicator=indicator)
    effect = RelatedIndicatorFactory.create(
        causal_indicator=indicator, effect_indicator__plans=[plan_with_pages], effect_indicator__common=None,
    )
    cause = RelatedIndicatorFactory.create(
        effect_indicator=indicator, causal_indicator__plans=[plan_with_pages], causal_indicator__common=None,
    )
    assert indicator.contact_persons.count() == 1
    assert plan_with_pages.dimensions.get() == plan_dimension
    assert indicator.dimensions.get() == indicator_dimension
    assert indicator_dimension.dimension == plan_dimension.dimension
    indicator.categories.add(category)
    indicator.save()

    # Copy
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)

    # There should be three indicators in the copy (indicator, its cause and effect)
    assert plan_with_pages.indicators.count() == 3
    assert plan_copy.indicators.count() == 3
    # Test indicator itself
    indicator_copy = plan_copy.indicators.get(name=indicator.name)
    assert indicator_copy != indicator
    assert indicator_copy.name == indicator.name
    # Test contact persons
    # We copy contact person through model instances but not Person instances
    assert indicator_copy.contact_persons.get() != indicator.contact_persons.get()
    assert indicator_copy.contact_persons_unordered.get() == indicator.contact_persons_unordered.get()
    # Test value
    value_copy = indicator_copy.values.get()
    assert value_copy != value
    assert value_copy.date == value.date
    assert value_copy.value == value.value
    # Test goal
    goal_copy = indicator_copy.goals.get()
    assert goal_copy != goal
    assert goal_copy.date == goal.date
    assert goal_copy.value == goal.value
    # Test action indicator (should point to copy of action)
    action_indicator_copy = indicator_copy.related_actions.get()
    assert action_indicator_copy.action != action_indicator.action
    assert action_indicator_copy.action.name == action_indicator.action.name
    assert action_indicator_copy.effect_type == action_indicator.effect_type
    assert action_indicator_copy.indicates_action_progress == action_indicator.indicates_action_progress
    # Test effect indicator
    effect_copy = indicator_copy.related_effects.get()
    assert effect_copy != effect
    assert effect_copy.causal_indicator == indicator_copy
    assert effect_copy.effect_indicator != effect.effect_indicator
    assert effect_copy.effect_indicator.name == effect.effect_indicator.name
    assert effect_copy.confidence_level == effect.confidence_level
    # Test cause indicator
    cause_copy = indicator_copy.related_causes.get()
    assert cause_copy != cause
    assert cause_copy.effect_indicator == indicator_copy
    assert cause_copy.causal_indicator != cause.causal_indicator
    assert cause_copy.causal_indicator.name == cause.causal_indicator.name
    assert cause_copy.confidence_level == cause.confidence_level
    # Test dimensions (dimensions are copied, not shared, when copy_indicators=True)
    indicator_dimension_copy = indicator_copy.dimensions.get()
    assert indicator_dimension_copy != indicator_dimension
    assert indicator_dimension_copy.indicator == indicator_copy
    dimension_copy = indicator_dimension_copy.dimension
    assert dimension_copy != dimension
    assert dimension_copy.name == dimension.name
    # Original dimension should only be linked to the original plan
    original_dimension_plan_ids = dimension.plans.values_list('plan_id', flat=True)
    assert list(original_dimension_plan_ids) == [plan_with_pages.id]
    # Copied dimension should only be linked to the copied plan
    copied_dimension_plan_ids = dimension_copy.plans.values_list('plan_id', flat=True)
    assert list(copied_dimension_plan_ids) == [plan_copy.id]
    # Test dimension categories (should be copied along with dimensions)
    dimension_category1_copy = dimension_copy.categories.get(name=dimension_category1.name)
    dimension_category2_copy = dimension_copy.categories.get(name=dimension_category2.name)
    assert dimension_category1_copy != dimension_category1
    assert dimension_category2_copy != dimension_category2
    # Test that indicator value categories reference the copied dimension categories
    assert set(value_copy.categories.all()) == {dimension_category1_copy, dimension_category2_copy}
    # Test indicator actions
    action_copy = plan_copy.actions.get()
    assert indicator_copy.actions.get() == action_copy
    # Test indicator categories
    category_copy = plan_copy.category_types.get().categories.get()
    assert indicator_copy.categories.get() == category_copy


@pytest.mark.parametrize('indicator__common', [None])
def test_copy_indicator_keeps_original_indicator_unchanged(plan_with_pages, indicator):
    # Original indicator should still belong to only the original plan
    assert plan_with_pages.indicators.get() == indicator
    copy_plan(plan_with_pages, copy_indicators=True)
    assert indicator.plans.get() == plan_with_pages


@pytest.mark.parametrize('indicator__common', [None])
def test_cannot_copy_indicators_when_shared(plan_with_pages, indicator):
    # When the original plan shares some indicators with another plan, copying should raise an error
    another_plan = PlanFactory.create()
    assert plan_with_pages.indicators.get() == indicator
    IndicatorLevelFactory.create(plan=another_plan, indicator=indicator)
    assert another_plan.indicators.get() == indicator
    assert indicator.plans.count() == 2
    with pytest.raises(ValueError, match='Cannot copy indicators as the plan shares indicators with another plan'):
        copy_plan(plan_with_pages, copy_indicators=True)


def test_cannot_copy_common_indicator_instances(plan_with_pages, indicator):
    # We decided not to copy organizations and common indicators. So the unique constraint on `(common_id,
    # organization_id)` in `Indicator` prevents us from copying indicators that are instances of a common indicator.
    assert indicator.common is not None
    assert plan_with_pages.indicators.get() == indicator
    with pytest.raises(ValueError, match='Cannot copy indicators as some are instances of a common indicator'):
        copy_plan(plan_with_pages, copy_indicators=True)


def test_rich_text_field_indicator_references(plan_with_pages):
    indicator1 = IndicatorFactory.create(plans=[plan_with_pages], common=None, description='foo')
    indicator2 = IndicatorFactory.create(plans=[plan_with_pages], common=None, description=html_with_references([indicator1]))
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)
    indicator1_copy = plan_copy.indicators.get(name=indicator1.name)
    indicator2_copy = plan_copy.indicators.get(name=indicator2.name)
    assert indicator1 != indicator1_copy
    assert indicator2 != indicator2_copy
    assert indicator1_copy.description == indicator1.description
    assert indicator2_copy.description == html_with_references([indicator1_copy])


@pytest.mark.parametrize('indicator__common', [None])
def test_indicator_reference_in_action_description_updated_when_copying_indicators(
    plan_with_pages, action, indicator,
):
    """When copying a plan with indicators, indicator references in action descriptions should be updated."""
    action.description = html_with_references([indicator])
    action.save(update_fields=['description'])
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)
    action_copy = plan_copy.actions.get()
    indicator_copy = plan_copy.indicators.get(name=indicator.name)
    assert action_copy.description == html_with_references([indicator_copy])


@pytest.mark.parametrize('indicator__common', [None])
def test_indicator_reference_in_action_draft_updated_when_copying_indicators(
    plan_with_pages, action, indicator, user,
):
    """When copying a plan with indicators, indicator references in action draft descriptions should be updated."""
    action.description = html_with_references([indicator])
    action.save(update_fields=['description'])
    action.save_revision(user=user)
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)
    action_copy = plan_copy.actions.get()
    assert action_copy.latest_revision is not None
    indicator_copy = plan_copy.indicators.get(name=indicator.name)
    draft_obj = action_copy.latest_revision.as_object()
    assert draft_obj.description == html_with_references([indicator_copy])


@pytest.mark.parametrize('indicator__common', [None])
def test_indicator_reference_in_action_task_comment_updated_when_copying_indicators(
    plan_with_pages, action, indicator,
):
    """When copying a plan with indicators, indicator references in action task comments should be updated."""
    task = ActionTaskFactory.create(action=action, comment=html_with_references([indicator]))
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)
    action_copy = plan_copy.actions.get()
    task_copy = action_copy.tasks.get(name=task.name)
    indicator_copy = plan_copy.indicators.get(name=indicator.name)
    assert task_copy.comment == html_with_references([indicator_copy])


@pytest.mark.parametrize('indicator__common', [None])
def test_indicator_reference_in_attribute_rich_text_updated_when_copying_indicators(
    plan_with_pages, action, indicator,
):
    """When copying a plan with indicators, indicator references in AttributeRichText.text should be updated."""
    action_ct = ContentType.objects.get_for_model(Action)
    plan_ct = ContentType.objects.get_for_model(Plan)
    attribute_type = AttributeTypeFactory.create(
        scope=plan_with_pages,
        object_content_type=action_ct,
        format=AttributeType.AttributeFormat.RICH_TEXT,
    )
    AttributeRichTextFactory.create(
        type=attribute_type,
        content_object=action,
        text=html_with_references([indicator]),
    )
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)
    indicator_copy = plan_copy.indicators.get(name=indicator.name)
    at_copy = AttributeType.objects.get(scope_content_type=plan_ct, scope_id=plan_copy.pk, name=attribute_type.name)
    rich_text_attr_copy = at_copy.rich_text_attributes.get()
    assert rich_text_attr_copy.text == html_with_references([indicator_copy])


@pytest.mark.parametrize('indicator__common', [None])
def test_indicator_reference_in_attribute_choice_with_text_updated_when_copying_indicators(
    plan_with_pages, action, indicator,
):
    """When copying a plan with indicators, indicator references in AttributeChoiceWithText.text should be updated."""
    action_ct = ContentType.objects.get_for_model(Action)
    plan_ct = ContentType.objects.get_for_model(Plan)
    attribute_type = AttributeTypeFactory.create(
        scope=plan_with_pages,
        object_content_type=action_ct,
        format=AttributeType.AttributeFormat.OPTIONAL_CHOICE_WITH_TEXT,
    )
    choice_option = AttributeTypeChoiceOptionFactory.create(type=attribute_type)
    AttributeChoiceWithTextFactory.create(
        type=attribute_type,
        content_object=action,
        choice=choice_option,
        text=html_with_references([indicator]),
    )
    plan_copy = copy_plan(plan_with_pages, copy_indicators=True)
    indicator_copy = plan_copy.indicators.get(name=indicator.name)
    at_copy = AttributeType.objects.get(scope_content_type=plan_ct, scope_id=plan_copy.pk, name=attribute_type.name)
    choice_with_text_attr_copy = at_copy.choice_with_text_attributes.get()
    assert choice_with_text_attr_copy.text == html_with_references([indicator_copy])


def test_action_revision_is_copied(plan_with_pages, action, user):
    action.save_revision(user=user)
    plan_copy = copy_plan(plan_with_pages)
    action_copy = plan_copy.actions.get()
    assert isinstance(action_copy.latest_revision, Revision)
    assert action_copy.latest_revision != action.latest_revision
    rev_obj = action_copy.latest_revision.as_object()
    assert rev_obj.pk == action_copy.pk
    assert rev_obj.uuid == action_copy.uuid
    assert rev_obj.name == action.name


def test_action_revision_references_are_updated(plan_with_pages, action, user):
    """The revision content should reference the copied plan, not the original."""
    action.save_revision(user=user)
    plan_copy = copy_plan(plan_with_pages)
    action_copy = plan_copy.actions.get()
    rev_obj = action_copy.latest_revision.as_object()
    assert rev_obj.plan_id == plan_copy.pk


def test_original_action_revision_is_unchanged(plan_with_pages, action, user):
    """Copying a plan must not modify the original action's revision."""
    action.save_revision(user=user)
    original_rev_pk = action.latest_revision.pk
    copy_plan(plan_with_pages)
    action.refresh_from_db()
    # The original action still points to the same revision
    assert action.latest_revision_id == original_rev_pk
    # The revision content is unchanged (references still point to the original plan)
    original_rev_obj = action.latest_revision.as_object()
    assert original_rev_obj.plan_id == plan_with_pages.pk
    assert original_rev_obj.pk == action.pk
    assert original_rev_obj.uuid == action.uuid


def test_non_clusterable_model_revision_is_copied(plan_with_pages):
    """
    Verify that revisions are copied for non-ClusterableModel RevisionMixin models.

    These models have i18n default_language_field that traverses a regular ForeignKey
    (not ParentalKey), e.g., 'plan__primary_language_lowercase'.
    """
    action_status = ActionStatusFactory.create(plan=plan_with_pages, name='On time')
    action_status.save_revision()
    original_rev = action_status.latest_revision
    plan_copy = copy_plan(plan_with_pages)
    status_copy = plan_copy.action_statuses.get(name='On time')
    # Revision is copied and points to the copy's plan
    assert status_copy.latest_revision is not None
    assert status_copy.latest_revision != original_rev
    rev_obj = status_copy.latest_revision.as_object()
    assert rev_obj.pk == status_copy.pk
    assert rev_obj.plan_id == plan_copy.pk
    # The original's revision is unchanged
    action_status.refresh_from_db()
    assert action_status.latest_revision == original_rev


def test_model_without_revision_is_not_affected(plan_with_pages, action):
    """Models without a latest_revision should not get a revision created by copying."""
    assert action.latest_revision is None
    plan_copy = copy_plan(plan_with_pages)
    action_copy = plan_copy.actions.get()
    assert action_copy.latest_revision is None


def test_report_type_attribute_field_references_are_updated(plan_with_pages):
    """When copying a plan, attribute_type references in ReportType.fields are updated to the copy."""
    action_ct = ContentType.objects.get_for_model(Action)
    attribute_type = AttributeTypeFactory.create(
        scope=plan_with_pages,
        object_content_type=action_ct,
    )
    ReportTypeFactory.create(
        plan=plan_with_pages,
        fields__0__attribute__attribute_type=attribute_type,
    )
    plan_copy = copy_plan(plan_with_pages)
    report_type_copy = plan_copy.report_types.get()
    attribute_field_copy = report_type_copy.fields[0]
    assert attribute_field_copy.block_type == 'attribute'
    attribute_type_copy = attribute_field_copy.value['attribute_type']
    assert attribute_type_copy.pk != attribute_type.pk
    assert attribute_type_copy.scope_id == plan_copy.pk


def test_report_type_category_field_references_are_updated(plan_with_pages):
    """When copying a plan, category_type references in ReportType.fields are updated to the copy."""
    category_type = CategoryTypeFactory.create(plan=plan_with_pages)
    ReportTypeFactory.create(
        plan=plan_with_pages,
        fields__0__categories__category_type=category_type,
    )
    plan_copy = copy_plan(plan_with_pages)
    report_type_copy = plan_copy.report_types.get()
    category_field_copy = report_type_copy.fields[0]
    assert category_field_copy.block_type == 'categories'
    category_type_copy = category_field_copy.value['category_type']
    assert category_type_copy.pk != category_type.pk
    assert category_type_copy.plan == plan_copy


def test_documentation_pages_are_copied(plan_with_pages):
    global_root = Page.get_first_root_node()
    assert global_root is not None
    doc_root = DocumentationRootPage(title='Documentation', plan=plan_with_pages, slug='docs')
    global_root.add_child(instance=doc_root)

    plan_copy = copy_plan(plan_with_pages)

    assert plan_copy.documentation_root_pages.count() == 1
    doc_root_copy = plan_copy.documentation_root_pages.get()
    assert doc_root_copy.pk != doc_root.pk
    assert doc_root_copy.plan == plan_copy


def test_documentation_pages_original_is_unchanged(plan_with_pages):
    global_root = Page.get_first_root_node()
    assert global_root is not None
    doc_root = DocumentationRootPage(title='Documentation', plan=plan_with_pages, slug='docs')
    global_root.add_child(instance=doc_root)

    copy_plan(plan_with_pages)

    doc_root.refresh_from_db()
    assert doc_root.plan == plan_with_pages
    assert plan_with_pages.documentation_root_pages.count() == 1


def test_copy_attribute_types_excludes_other_plans_category_type_scoped_attribute_types(plan_with_pages):
    # AttributeType uses a generic foreign key for its scope, so _copy_attribute_types must filter by
    # scope_id__in=plan.category_types.all() to avoid accidentally copying attribute types that belong
    # to another plan's category types. A regression in that filter could silently copy foreign attribute
    # types into the plan copy, corrupting the copied plan's data.
    category_type = CategoryTypeFactory.create(plan=plan_with_pages)
    attribute_type = AttributeTypeFactory.create(scope=category_type)

    other_plan = PlanFactory.create()
    other_category_type = CategoryTypeFactory.create(plan=other_plan)
    other_attribute_type = AttributeTypeFactory.create(scope=other_category_type)

    plan_copy = copy_plan(plan_with_pages)

    category_type_ct = ContentType.objects.get_for_model(CategoryType)
    category_type_copy = plan_copy.category_types.get()
    copied_ats = AttributeType.objects.filter(scope_content_type=category_type_ct, scope_id=category_type_copy.pk)
    assert copied_ats.count() == 1
    assert copied_ats.get().pk != attribute_type.pk

    # The other plan's attribute type must not be copied or modified
    other_ats = AttributeType.objects.filter(scope_content_type=category_type_ct, scope_id=other_category_type.pk)
    assert other_ats.count() == 1
    assert other_ats.get() == other_attribute_type


class TestUpdateReferenceIndexImmediately:
    def test_forces_immediate_indexing(self, plan_with_pages, static_page):
        doc = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc')
        # StaticPage is tracked by Wagtail's reference index.
        # Without the context manager, the index update is deferred to transaction commit,
        # which never happens in test transactions — so the index stays empty.
        static_page.body = [('paragraph', RichText(html_with_references([doc])))]
        static_page.save()
        assert list(ReferenceIndex.get_references_for_object(static_page)) == []

        # With the context manager, enqueue_on_commit=False causes the index to be updated immediately.
        with _update_reference_index_immediately_ctx():
            static_page.save()
        refs = list(ReferenceIndex.get_references_for_object(static_page))
        assert any(str(ref.to_object_id) == str(doc.pk) for ref in refs)

    def test_update_indexed_references_uses_immediate_index(self, plan_with_pages, static_page):
        doc = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc')
        # doc_copy uses the same title so html_with_references produces the same text content.
        doc_copy = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc')

        static_page.body = [('paragraph', RichText(html_with_references([doc])))]

        clone_visitor = CloneVisitor(site_hostname='copy.example.com')
        clone_visitor.register_copy(doc, doc_copy)
        # Register static_page as a "copy" so _update_stream_field_reference allows modifying it.
        fake_original = StaticPage(pk=static_page.pk + 999999)
        clone_visitor.register_copy(fake_original, static_page)

        # Save within the context manager so the reference index is updated immediately.
        with _update_reference_index_immediately_ctx():
            static_page.save()

        fields = UpdateReferencesVisitor(clone_visitor).update_indexed_references(static_page)
        assert 'body' in fields
        assert static_page.body[0].value.source == html_with_references([doc_copy])

    def test_without_decorator_leaves_stale_rich_text_references(self, plan_with_pages, static_page):
        doc = AplansDocumentFactory.create(collection=plan_with_pages.root_collection, title='doc')
        static_page.body = [('paragraph', RichText(html_with_references([doc])))]
        static_page.save()

        new_plan_identifier = plan_with_pages.default_identifier_for_copying()
        new_plan_name = plan_with_pages.default_name_for_copying()
        new_site_hostname = _new_site_hostname(plan_with_pages, new_plan_identifier)
        clone_visitor = CloneVisitor(
            site_hostname=new_site_hostname,
            plan_identifier=new_plan_identifier,
            plan_name=new_plan_name,
        )

        # Call _clone_plan_objects directly without the @update_reference_index_immediately decorator.
        with transaction.atomic():
            plan_copy = _clone_plan_objects(plan_with_pages, clone_visitor, None, copy_indicators=False)

        page_copy = plan_copy.root_page.get_children().type(StaticPage).get().specific
        assert isinstance(page_copy, StaticPage)
        doc_copy = AplansDocument.objects.get(collection=plan_copy.root_collection, title=doc.title)
        # Without the decorator, update_indexed_references() finds nothing in the un-updated index.
        # The page copy's body still references the original doc pk (stale reference).
        assert page_copy.body[0].value.source == html_with_references([doc])
        assert page_copy.body[0].value.source != html_with_references([doc_copy])
