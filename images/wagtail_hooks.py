from wagtail.core import hooks
from images.permissions import permission_policy


@hooks.register('construct_image_chooser_queryset')
def filter_images(qs, request):
    user = request.user
    collections = permission_policy.collections_user_has_any_permission_for(user, ['choose'], request=request)
    qs = qs.filter(collection__in=collections)
    return qs
