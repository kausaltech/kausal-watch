from wagtail.test.utils.wagtail_factories import DocumentFactory


class AplansDocumentFactory(DocumentFactory):
    class Meta:
        model = 'documents.AplansDocument'
