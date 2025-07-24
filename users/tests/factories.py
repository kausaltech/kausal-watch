from django.contrib.auth.hashers import make_password

from factory.declarations import LazyFunction, Sequence
from factory.django import DjangoModelFactory

from users.models import User


class UserFactory(DjangoModelFactory[User]):
    class Meta:
        model = User

    email = Sequence(lambda i: f'user{i}@example.com')
    password = LazyFunction(lambda: make_password('foobar'))
    is_staff = True
    is_superuser = False
