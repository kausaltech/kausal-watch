from __future__ import annotations

from django.urls import path

from .views import SetPasswordView

urlpatterns = [
    path(
        'access-requests/<int:pk>/password/<uidb64>/<token>/',
        SetPasswordView.as_view(),
        name='access_requests_set_password',
    ),
]
