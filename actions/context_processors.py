def current_plan(request):
    from admin_site.models import Client

    out = {}
    if not request or not request.user or not request.user.is_authenticated:
        return out
    out['active_plan'] = request.user.get_active_admin_plan()
    out['active_client'] = Client.objects.for_request(request).first()
    return out
