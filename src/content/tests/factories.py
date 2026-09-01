from django.db.models.signals import post_save

import factory
from factory import SubFactory
from factory.django import DjangoModelFactory

from actions.models import Plan
from actions.tests.factories import PlanFactory
from content.models import SiteGeneralContent


# https://factoryboy.readthedocs.io/en/stable/recipes.html#example-django-s-profile
@factory.django.mute_signals(post_save)
class SiteGeneralContentFactory(DjangoModelFactory[SiteGeneralContent]):
    class Meta:
        model = 'content.SiteGeneralContent'

    plan = SubFactory[SiteGeneralContent, Plan](PlanFactory, general_content=None)
