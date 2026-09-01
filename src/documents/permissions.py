from wagtail.documents import get_document_model
from wagtail.documents.models import Document

from admin_site.permissions import PlanRelatedCollectionOwnershipPermissionPolicy

permission_policy = PlanRelatedCollectionOwnershipPermissionPolicy(
    get_document_model(),
    auth_model=Document,
    owner_field_name='uploaded_by_user',
)
