def current_plan(request):
    from admin_site.models import Client

    out = {}
    if not request or not request.user or not request.user.is_authenticated:
        return out
    if getattr(request, '_active_plan', None):
        plan = request._active_plan
    else:
        plan = request.user.get_active_admin_plan()
        request._active_plan = plan
    if getattr(request, '_active_client', None):
        client = request._active_client
    else:
        client = Client.objects.for_request(request).first()
        request._active_client = client

    out['active_plan'] = plan
    out['active_client'] = client
    return out
