from typing import TypeVar, Generic
from factory.django import DjangoModelFactory


T = TypeVar("T")


class ModelFactory(Generic[T], DjangoModelFactory):
    @classmethod
    def create(cls, **kwargs) -> T:
        return super().create(**kwargs)
