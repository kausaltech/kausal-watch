from __future__ import annotations

from wagtail.models import Revision

import pytest

from actions.tests.factories import ActionContactFactory, WorkflowFactory
from copying.main import copy_plan
from documents.models import AplansDocument
from documents.tests.factories import AplansDocumentFactory
from images.models import AplansImage
from images.tests.factories import AplansImageFactory
from pages.tests.factories import CategoryTypePageLevelLayoutFactory

pytestmark = pytest.mark.django_db


def get_page_copy(page, plan_copy):
    page_copy = plan_copy.root_page.get_children().get(url_path=page.url_path).specific
    assert type(page_copy) is type(page)
    return page_copy


def html_with_references(doc1, doc2, image1, image2):
    """Return HTML with references as Wagtail would produce it in a rich-text field."""
    return f"""
<p data-block-key="foo">
<a linktype="document" id="{doc1.pk}">doc1</a>
<a linktype="document" id="{doc2.pk}">doc2</a>
<embed embedtype="image" format="fullwidth-zoomable" id="{image1.pk}" alt="image1"/>
<embed embedtype="image" format="fullwidth-zoomable" id="{image2.pk}" alt="image2"/>
</p>'
""".replace('\n', '')


def test_publish_copied_action_does_not_steal_contact_persons(plan_with_pages, action, user):
    ActionContactFactory(action=action)
    plan = plan_with_pages
    plan.features.moderation_workflow = WorkflowFactory()
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
    CategoryTypePageLevelLayoutFactory(
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


def test_rich_text_field_references(plan_with_pages, action):
    doc1 = AplansDocumentFactory(collection=plan_with_pages.root_collection, title='doc1')
    doc2 = AplansDocumentFactory(collection=plan_with_pages.root_collection, title='doc2')
    image1 = AplansImageFactory(collection=plan_with_pages.root_collection, title='image1')
    image2 = AplansImageFactory(collection=plan_with_pages.root_collection, title='image2')
    action.description = html_with_references(doc1, doc2, image1, image2)
    action.save(update_fields=['description'])
    plan_copy = copy_plan(plan_with_pages)
    doc1_copy = AplansDocument.objects.get(collection=plan_copy.root_collection, title=doc1.title)
    doc2_copy = AplansDocument.objects.get(collection=plan_copy.root_collection, title=doc2.title)
    image1_copy = AplansImage.objects.get(collection=plan_copy.root_collection, title=image1.title)
    image2_copy = AplansImage.objects.get(collection=plan_copy.root_collection, title=image2.title)
    action_copy = plan_copy.actions.get()
    assert action_copy.description == html_with_references(doc1_copy, doc2_copy, image1_copy, image2_copy)
