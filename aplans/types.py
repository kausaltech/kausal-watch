from django.http import HttpRequest
from users.models import User


class WatchRequest(HttpRequest):
    pass


class WatchAdminRequest(WatchRequest):
    user: User
