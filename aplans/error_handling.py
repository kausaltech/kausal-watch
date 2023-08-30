from django.views.defaults import server_error as html_server_error
from rest_framework.exceptions import server_error as json_server_error


def server_error(request, *args, **kwargs):
    if request.accepts('text/html'):
        return html_server_error(request, *args, **kwargs)
    elif request.accepts('application/json'):
        return json_server_error(request, *args, **kwargs)
    return html_server_error(request, *args, **kwargs)
