from admin_site.permissions import PlanRelatedCollectionOwnershipPermissionPolicy
from wagtail.images import get_image_model
from wagtail.images.models import Image

permission_policy = PlanRelatedCollectionOwnershipPermissionPolicy(
    get_image_model(),
    auth_model=Image,
    owner_field_name='uploaded_by_user'
)
