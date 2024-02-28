from django.http import HttpResponseServerError
from django.views.defaults import ERROR_500_TEMPLATE_NAME
from django.conf import settings
from rest_framework.exceptions import server_error as json_server_error
from django.views.decorators.csrf import requires_csrf_token
from django.template import loader
import sentry_sdk

from actions.context_processors import current_plan
from admin_site.context_processors import sentry


@requires_csrf_token
def html_server_error(request, template_name=ERROR_500_TEMPLATE_NAME):
    """
    500 error handler.

    Templates: :template:`500.html`
    Context: None
    """
    context = {}
    try:
        ret = current_plan(request)
        if ret:
            context.update(ret)
    except Exception:
        pass
    try:
        ret = sentry(request)
        if ret:
            context.update(ret)
    except Exception:
        pass

    context['sentry_error_id'] = None
    if settings.SENTRY_DSN:
        context['sentry_error_id'] = sentry_sdk.last_event_id()
    template = loader.get_template(template_name)
    return HttpResponseServerError(template.render(context=context, request=request))


def server_error(request, *args, **kwargs):
    if request.accepts('text/html'):
        return html_server_error(request, *args, **kwargs)
    elif request.accepts('application/json'):
        return json_server_error(request, *args, **kwargs)
    return html_server_error(request, *args, **kwargs)
