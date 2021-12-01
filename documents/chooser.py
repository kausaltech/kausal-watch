from django.core.paginator import Paginator
from django.template.response import TemplateResponse
from django.urls import reverse
from django.utils.translation import gettext as _

from wagtail.admin.forms.search import SearchForm
from wagtail.admin.modal_workflow import render_modal_workflow
from wagtail.core import hooks
from wagtail.core.models import Collection
from wagtail.documents import get_document_model
from wagtail.documents.forms import get_document_form
from wagtail.documents.permissions import permission_policy

_wagtail_get_chooser_context = None


def chooser(request):
    Document = get_document_model()

    if permission_policy.user_has_permission(request.user, 'add'):
        DocumentForm = get_document_form(Document)
        uploadform = DocumentForm(user=request.user, prefix='document-chooser-upload')
    else:
        uploadform = None

    documents = Document.objects.all()

    # allow hooks to modify the queryset
    for hook in hooks.get_hooks('construct_document_chooser_queryset'):
        documents = hook(documents, request)

    q = None
    if 'q' in request.GET or 'p' in request.GET or 'collection_id' in request.GET:

        collection_id = request.GET.get('collection_id')
        if collection_id:
            documents = documents.filter(collection=collection_id)
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
        documents = paginator.get_page(request.GET.get('p'))

        return TemplateResponse(request, "wagtaildocs/chooser/results.html", {
            'documents': documents,
            'documents_exist': documents_exist,
            'uploadform': uploadform,
            'query_string': q,
            'is_searching': is_searching,
            'collection_id': collection_id,
        })
    else:
        searchform = SearchForm()

        plan = request.user.get_active_admin_plan()
        if plan.root_collection is not None:
            collections = plan.root_collection.get_descendants(inclusive=True)
        else:
            collections = []

        if len(collections) < 2:
            collections = None
        else:
            collections = Collection.order_for_display(collections)

        documents = documents.order_by('-created_at')
        documents_exist = documents.exists()
        paginator = Paginator(documents, per_page=10)
        documents = paginator.get_page(request.GET.get('p'))

        return render_modal_workflow(request, 'wagtaildocs/chooser/chooser.html', None, {
            'documents': documents,
            'documents_exist': documents_exist,
            'uploadform': uploadform,
            'searchform': searchform,
            'collections': collections,
            'is_searching': False,
        }, json_data={
            'step': 'chooser',
            'error_label': _("Server Error"),
            'error_message': _("Report this error to your webmaster with the following information:"),
            'tag_autocomplete_url': reverse('wagtailadmin_tag_autocomplete'),
        })


def monkeypatch_chooser():
    from wagtail.documents.views import chooser as wagtail_chooser

    wagtail_chooser.chooser = chooser

