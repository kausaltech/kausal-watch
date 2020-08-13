from os import path
from django.core.exceptions import ObjectDoesNotExist
from django.utils.html import escape

from wagtail.core import hooks
from wagtail.core.rich_text import LinkHandler
from wagtail.documents import get_document_model


class DocumentLinkHandler(LinkHandler):
    identifier = 'document'

    @staticmethod
    def get_model():
        return get_document_model()

    @classmethod
    def expand_db_attributes(cls, attrs):
        try:
            doc = cls.get_instance(attrs)
        except (ObjectDoesNotExist, KeyError):
            return "<a>"
        base, ext = path.splitext(doc.file.name)
        ext = ext.lstrip('.')
        return '<a href="%s" data-link-type="document" data-file-extension="%s">' % (escape(doc.url), escape(ext))


@hooks.register('register_rich_text_features')
def register_document_feature(features):
    features.register_link_type(DocumentLinkHandler)
