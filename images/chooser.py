from wagtail.core.models import Collection


_wagtail_get_chooser_context = None


def get_chooser_context(request):
    ret = _wagtail_get_chooser_context(request)

    plan = request.user.get_active_admin_plan()
    if plan.root_collection is not None:
        collections = plan.root_collection.get_descendants(inclusive=True)
    else:
        collections = []

    if len(collections) < 2:
        collections = None
    else:
        collections = Collection.order_for_display(collections)

    ret['collections'] = collections
    return ret


def monkeypatch_chooser():
    from wagtail.images.views import chooser
    global _wagtail_get_chooser_context

    if _wagtail_get_chooser_context is not None:
        return

    _wagtail_get_chooser_context = chooser.get_chooser_context
    chooser.get_chooser_context = get_chooser_context
