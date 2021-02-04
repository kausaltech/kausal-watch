from wagtail.core import hooks


@hooks.register('construct_image_chooser_queryset')
def filter_images(qs, request):
    user = request.user
    plan = user.get_active_admin_plan()
    collections = plan.root_collection.get_descendants(inclusive=True)
    qs = qs.filter(collection__in=collections)
    return qs
