from __future__ import annotations

from os import path
from typing import TYPE_CHECKING, List, cast

from django.utils.html import escape
from wagtail import hooks
from wagtail.documents.rich_text import DocumentLinkHandler as WagtailDocumentLinkHandler

if TYPE_CHECKING:
    from .models import AplansDocument


class DocumentLinkHandler(WagtailDocumentLinkHandler):
    identifier = 'document'

    @classmethod
    def expand_one(cls, doc: AplansDocument) -> str:
        base, ext = path.splitext(doc.file.name)
        ext = ext.lstrip('.')
        return '<a href="%s" data-link-type="document" data-file-extension="%s">' % (escape(doc.url), escape(ext))

    @classmethod
    def expand_db_attributes_many(cls, attrs_list: list[dict]) -> list[str]:
        ret = [
            cls.expand_one(cast('AplansDocument', doc)) if doc else "<a>"
            for doc in cls.get_many(attrs_list)
        ]
        return ret


def register_document_feature(features):
    features.register_link_type(DocumentLinkHandler)

hooks.register('register_rich_text_features', register_document_feature)
