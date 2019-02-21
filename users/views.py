from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.urls import reverse
from actions.models import Plan


@require_http_methods(["POST"])
@login_required
def change_admin_plan(request):
    user = request.user
    plans = user.get_adminable_plans()
    plan = request.POST.get('plan', None)
    if plan is None:
        return HttpResponseBadRequest("No plan given")
    try:
        plan_id = int(plan)
    except ValueError:
        return HttpResponseBadRequest("Invalid plan id")

    for plan in plans:
        if plan.id == plan_id:
            break
    else:
        return HttpResponseBadRequest("Not allowed plan id")

    user = request.user
    user.selected_admin_plan = plan
    user.save(update_fields=['selected_admin_plan'])

    return HttpResponseRedirect(reverse('admin:index'))
