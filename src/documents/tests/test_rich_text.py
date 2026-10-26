from wagtail.rich_text import expand_db_html

import pytest

from actions.tests.factories import PlanFactory
from documents.tests.factories import AplansDocumentFactory


@pytest.mark.django_db
def test_document_link_has_link_type_attributes():
    plan = PlanFactory.create()
    document = AplansDocumentFactory.create(collection=plan.root_collection)

    html = expand_db_html(f'<a linktype="document" id="{document.pk}">doc</a>')

    assert 'data-link-type="document"' in html
    assert 'data-file-extension=' in html
