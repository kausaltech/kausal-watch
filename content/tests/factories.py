from factory import SubFactory
from factory.django import DjangoModelFactory


# https://factoryboy.readthedocs.io/en/stable/recipes.html#example-django-s-profile
# @factory.django.mute_signals(post_save)
"""
FIXME: Will this still be needed?

class SiteGeneralContentFactory(DjangoModelFactory):
    class Meta:
        model = 'content.SiteGeneralContent'

    plan = SubFactory('actions.tests.factories.PlanFactory', general_content=None)
"""
