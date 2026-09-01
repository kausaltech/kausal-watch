from wagtail.images import get_image_model
from wagtail.images.models import Image

from admin_site.permissions import PlanRelatedCollectionOwnershipPermissionPolicy

permission_policy = PlanRelatedCollectionOwnershipPermissionPolicy(
    get_image_model(),
    auth_model=Image,
    owner_field_name='uploaded_by_user',
)
