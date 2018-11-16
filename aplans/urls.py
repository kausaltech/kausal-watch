"""aplans URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/2.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.views.decorators.csrf import csrf_exempt
from markdownx.views import ImageUploadView, MarkdownifyView
from rest_framework import routers

from actions.api import all_views as actions_api_views
from indicators.api import all_views as indicators_api_views


router = routers.DefaultRouter()
for view in actions_api_views + indicators_api_views:
    router.register(view['name'], view['class'])


urlpatterns = [
    path('admin/', admin.site.urls),
    path('markdownx/upload/', ImageUploadView.as_view(), name='markdownx_upload'),
    path('markdownx/markdownify/', csrf_exempt(MarkdownifyView.as_view()), name='markdownx_markdownify'),
    path('v1/', include(router.urls)),
    path('', include('social_django.urls', namespace='social'))
]
