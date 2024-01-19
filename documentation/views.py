from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from django.template.response import TemplateResponse

from .models import DocumentationPage


def index(request, page_id):
    page = get_object_or_404(DocumentationPage, id=page_id)
    page_plan = page.get_parent().specific.plan
    active_plan = request.user.get_active_admin_plan()
    if active_plan != page_plan:
        raise PermissionDenied()
    context = {
        'page': page,
    }
    return TemplateResponse(request, 'documentation/base.html', context)
