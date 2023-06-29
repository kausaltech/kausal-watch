def current_plan(request):
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
        person = request.user.get_corresponding_person()
        if person:
            client = person.get_admin_client()
        else:
            client = None
        request._active_client = client

    out['active_plan'] = plan
    out['active_client'] = client
    return out
