import factory
from django.db.models.signals import post_save
from factory import SubFactory
from factory.django import DjangoModelFactory

from actions.tests.factories import PlanFactory


# https://factoryboy.readthedocs.io/en/stable/recipes.html#example-django-s-profile
@factory.django.mute_signals(post_save)
class SiteGeneralContentFactory(DjangoModelFactory):
    class Meta:
        model = 'content.SiteGeneralContent'

    plan = SubFactory(PlanFactory, general_content=None)
