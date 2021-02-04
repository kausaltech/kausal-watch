from admin_site.permissions import PlanRelatedCollectionOwnershipPermissionPolicy
from wagtail.documents import get_document_model
from wagtail.documents.models import Document


permission_policy = PlanRelatedCollectionOwnershipPermissionPolicy(
    get_document_model(),
    auth_model=Document,
    owner_field_name='uploaded_by_user'
)
