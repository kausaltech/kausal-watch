from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from factory import LazyFunction, Sequence
from factory.django import DjangoModelFactory


class UserFactory(DjangoModelFactory):
    class Meta:
        model = get_user_model()

    email = Sequence(lambda i: f'user{i}@example.com')
    password = LazyFunction(lambda: make_password('foobar'))
    is_staff = True
    is_superuser = False
