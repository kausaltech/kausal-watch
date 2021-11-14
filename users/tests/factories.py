from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from factory import Sequence, SubFactory, LazyFunction, post_generation
from factory.django import DjangoModelFactory

from orgs.tests.factories import OrganizationFactory


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()

    email = Sequence(lambda i: f'user{i}@example.com')
    password = LazyFunction(lambda: make_password('foobar'))
    is_staff = True
    is_superuser = False

    @post_generation
    def general_admin_plans(self, create, extracted, **kwargs):
        if create and extracted:
            for plan in extracted:
                self.general_admin_plans.add(plan)
