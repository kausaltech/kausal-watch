from __future__ import annotations

from typing import TYPE_CHECKING

from wagtail import hooks

from documents.rich_text import DocumentLinkHandler

if TYPE_CHECKING:
    from wagtail.rich_text.feature_registry import FeatureRegistry


@hooks.register('register_rich_text_features', order=1)
def register_document_link_handler(features: FeatureRegistry):
    features.register_link_type(DocumentLinkHandler)


@hooks.register('construct_document_chooser_queryset')
def filter_documents(qs, request):
    user = request.user
    plan = user.get_active_admin_plan()
    collections = plan.root_collection.get_descendants(inclusive=True)
    qs = qs.filter(collection__in=collections)
    return qs
