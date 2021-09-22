from django.http import HttpResponse, Http404
from django.views.decorators.cache import cache_control

from .models import CategoryIcon


@cache_control(public=True, max_age=7 * 24 * 3600)
def category_icon(request, id: int):
    try:
        icon = CategoryIcon.objects.values('data').get(id=id)
    except CategoryIcon.DoesNotExist:
        raise Http404()

    return HttpResponse(icon['data'], content_type='image/svg+xml')
