from typing import TYPE_CHECKING, Any, cast

from django.core.paginator import Paginator
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext as _
from wagtail import hooks
from wagtail.admin.forms.search import SearchForm
from wagtail.admin.modal_workflow import render_modal_workflow
from wagtail.documents import get_document_model
from wagtail.documents.forms import get_document_form
from wagtail.documents.permissions import permission_policy
from wagtail.models import Collection

from kausal_common.users import user_or_bust

if TYPE_CHECKING:
    from django.http import HttpRequest
    from wagtail.models.media import CollectionQuerySet

    from documents.models import AplansDocumentQuerySet

    from .models import AplansDocument as DocumentModel

_wagtail_get_chooser_context: object | None = None


def chooser(request: HttpRequest):
    Document = cast('DocumentModel', get_document_model())

    if permission_policy.user_has_permission(request.user, 'add'):
        DocumentForm = get_document_form(Document)
        uploadform = DocumentForm(user=request.user, prefix='document-chooser-upload')
    else:
        uploadform = None

    documents = Document.objects.get_queryset().all()

    # allow hooks to modify the queryset
    for hook in hooks.get_hooks('construct_document_chooser_queryset'):
        documents = cast('AplansDocumentQuerySet', hook(documents, request))

    q = None
    if 'q' in request.GET or 'p' in request.GET or 'collection_id' in request.GET:
        collection_id = request.GET.get('collection_id')
        if collection_id:
            documents = documents.filter(collection=int(collection_id))
        documents_exist = documents.exists()

        searchform = SearchForm(request.GET)
        if searchform.is_valid():
            q = searchform.cleaned_data['q']

            documents = documents.search(q)
            is_searching = True
        else:
            documents = documents.order_by('-created_at')
            is_searching = False

        # Pagination
        paginator = Paginator(documents, per_page=10)
        document_list = paginator.get_page(request.GET.get('p'))

        return TemplateResponse(
            request,
            'wagtaildocs/chooser/results.html',
            {
                'documents': document_list,
                'documents_exist': documents_exist,
                'uploadform': uploadform,
                'query_string': q,
                'is_searching': is_searching,
                'collection_id': collection_id,
            },
        )
    searchform = SearchForm()

    user = user_or_bust(request.user)
    plan = user.get_active_admin_plan()
    collections: CollectionQuerySet | None = None
    if plan.root_collection is not None:
        collections = plan.root_collection.get_descendants(inclusive=True)
    else:
        collections = Collection.objects.get_queryset().none()

    if len(collections) < 2:
        collections = None
    else:
        collections = cast('CollectionQuerySet', cast('Any', Collection).order_for_display(collections))

    documents = documents.order_by('-created_at')
    documents_exist = documents.exists()
    paginator = Paginator(documents, per_page=10)
    documents_list = paginator.get_page(request.GET.get('p'))

    return render_modal_workflow(
        request,
        'wagtaildocs/chooser/chooser.html',
        None,
        {
            'documents': documents_list,
            'documents_exist': documents_exist,
            'uploadform': uploadform,
            'searchform': searchform,
            'collections': collections,
            'is_searching': False,
        },
        json_data={
            'step': 'chooser',
            'error_label': _('Server Error'),
            'error_message': _('Report this error to your webmaster with the following information:'),
            'tag_autocomplete_url': reverse('wagtailadmin_tag_autocomplete'),
        },
    )


def monkeypatch_chooser():
    from wagtail.documents.views import chooser as wagtail_chooser

    wagtail_chooser.chooser = chooser
