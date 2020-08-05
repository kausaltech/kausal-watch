from django.http import HttpResponseRedirect, HttpResponseBadRequest
from django.views.decorators.http import require_http_methods
from django.contrib.auth.decorators import login_required
from django.urls import reverse


@require_http_methods(['POST', 'GET'])
@login_required
def change_admin_plan(request, plan_id=None):
    user = request.user
    plans = user.get_adminable_plans()

    if request.method == 'POST':
        plan = request.POST.get('plan', None)
    else:
        plan = plan_id

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

    admin_type = request.GET.get('admin', 'django')
    if admin_type == 'wagtail':
        return HttpResponseRedirect(reverse('wagtailadmin_home'))
    else:
        return HttpResponseRedirect(reverse('admin:index'))
