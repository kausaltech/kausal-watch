from __future__ import annotations

from abc import abstractmethod
from typing import TYPE_CHECKING

from rest_framework import permissions

from kausal_common.users import user_or_none

if TYPE_CHECKING:
    from django.db.models import Model
    from django.views.generic import View
    from rest_framework.request import Request
    from rest_framework.views import APIView

    from users.models import User


class AnonReadOnly(permissions.BasePermission):
    def has_permission(self, request, view):
        return request.method in permissions.SAFE_METHODS


class WatchObjectPermissions(permissions.DjangoObjectPermissions):
    model: type[Model]

    def check_permission(self, perm: str, user: User, view: APIView, obj: Model | None = None) -> bool:
        """
        Return true if the user has the permission `perm`.

        If `obj` is None, we check model permissions, otherwise for permissions on the given object.
        """
        raise NotImplementedError('Implement in subclass!')

    def check_permissions(self, perms: list[str], request: Request, view: APIView, obj: Model | None = None):
        """
        Return true if the user has all permissions in `perms`.

        If `obj` is None, this checks model permissions, otherwise object permissions.
        """
        if not perms and request.method in permissions.SAFE_METHODS:
            return True
        user = user_or_none(request.user)
        if user is None:
            return False
        return all(self.check_permission(perm, user, view, obj) for perm in perms)

    def has_permission(self, request: Request, view: APIView):
        if not request.method:
            return False
        perms = self.get_required_permissions(request.method, self.model)
        return self.check_permissions(perms, request, view)

    def has_object_permission(self, request: Request, view: APIView, obj: Model):
        if request.method is None:
            return False
        perms = self.get_required_object_permissions(request.method, self.model)
        return self.check_permissions(perms, request, view, obj)
