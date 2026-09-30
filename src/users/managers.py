"""
User manager with email as username.

Django's default user manager treats usernames and emails separately and causes
the `createsuperuser` command to fail.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.contrib.auth.base_user import BaseUserManager

if TYPE_CHECKING:
    from .models import User


class UserManager(BaseUserManager['User']):
    use_in_migrations = True

    def get_by_natural_key(self, username: str | None) -> User:
        """
        Look the user up by email, ignoring case unless that is ambiguous.

        Login forms lowercase the email, but stored emails can have capitals. An exact match wins; otherwise a
        case-insensitive match is used only when exactly one user has that email.
        """
        exact = self.filter(email=username).first()
        if exact is not None:
            return exact
        matches = list(self.filter(email__iexact=username)[:2])
        if len(matches) != 1:
            raise self.model.DoesNotExist
        return matches[0]

    def _create_user(self, email, password=None, **extra_fields) -> User:
        if not email:
            raise ValueError('Users must have an email address')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra_fields) -> User:
        extra_fields.setdefault('is_superuser', False)
        return self._create_user(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields) -> User:
        extra_fields.setdefault('is_superuser', True)
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superusers must have is_superuser set to True')
        return self._create_user(email, password, **extra_fields)
