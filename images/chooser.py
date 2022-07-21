from wagtail.core.models import Collection


_wagtail_get_context_data = None


def get_context_data(self):
    ret = _wagtail_get_context_data(self)

    plan = self.request.user.get_active_admin_plan()
    if plan.root_collection is not None:
        collections = plan.root_collection.get_descendants(inclusive=True)
    else:
        collections = Collection.objects.none()

    if self.request.user.is_superuser:
        collections |= Collection.objects.filter(common_category_type__isnull=False)

    if len(collections) < 2:
        collections = None
    ret['collections'] = collections
    if 'popular_tags' in ret:
        ret['popular_tags'] = []
    return ret


def monkeypatch_chooser():
    from wagtail.images.views.chooser import ChooseView
    global _wagtail_get_context_data

    if _wagtail_get_context_data is not None:
        return

    _wagtail_get_context_data = ChooseView.get_context_data
    ChooseView.get_context_data = get_context_data
