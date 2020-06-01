def current_plan(request):
    out = {}
    if not request or not request.user or not request.user.is_authenticated:
        return out
    out['active_plan'] = request.user.get_active_admin_plan()
    return out
