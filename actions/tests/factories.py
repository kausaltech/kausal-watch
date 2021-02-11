# from django.contrib.auth import get_user_model
from factory import SubFactory
from factory.django import DjangoModelFactory


class OrganizationFactory(DjangoModelFactory):
    class Meta:
        model = 'django_orghierarchy.Organization'


class PlanFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Plan'

    organization = SubFactory(OrganizationFactory)
    name = "Test plan"
    identifier = 'test-plan'
    site_url = 'http://example.com'


class ActionFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Action'

    plan = SubFactory(PlanFactory)
    name = "Test action"
    identifier = 'test-action'
    official_name = name


class CategoryTypeFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.CategoryType'

    plan = SubFactory(PlanFactory)


class CategoryFactory(DjangoModelFactory):
    class Meta:
        model = 'actions.Category'

    type = SubFactory(CategoryTypeFactory)
    identifier = 'test-category'
    name = "Test category"


# class UserFactory(DjangoModelFactory):
#     class Meta:
#         model = get_user_model()
