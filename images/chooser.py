import functools
from wagtail.models import Collection


_wagtail_chooser_get_context_data = None
_wagtail_index_get_context_data = None

def get_context_data(self, get_context_func):
    ret = get_context_func(self)

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
    from wagtail.images.views.chooser import ImageChooseView
    from wagtail.images.views.images import IndexView
    global _wagtail_chooser_get_context_data, _wagtail_index_get_context_data

    if _wagtail_chooser_get_context_data is None:
        _wagtail_chooser_get_context_data = ImageChooseView.get_context_data
        ImageChooseView.get_context_data = functools.partialmethod(get_context_data, _wagtail_chooser_get_context_data)

    if _wagtail_index_get_context_data is None:
        _wagtail_index_get_context_data = IndexView.get_context_data
        IndexView.get_context_data = functools.partialmethod(get_context_data, _wagtail_index_get_context_data)
