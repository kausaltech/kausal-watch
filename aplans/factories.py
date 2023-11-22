# https://github.com/FactoryBoy/factory_boy/issues/468#issuecomment-1536373442
from typing import Generic, Type, TypeVar, get_args
from factory.base import FactoryMetaClass
from factory.django import DjangoModelFactory

T = TypeVar("T")


class BaseFactoryMeta(FactoryMetaClass):
    def __new__(mcs, class_name, bases: list[Type], attrs):
        orig_bases = attrs.get("__orig_bases__", [])
        for t in orig_bases:
            if t.__name__ == "ModelFactory" and t.__module__ == __name__:
                type_args = get_args(t)
                if len(type_args) == 1:
                    if "Meta" not in attrs:
                        attrs["Meta"] = type("Meta", (), {})
                    setattr(attrs["Meta"], "model", type_args[0])
                    setattr(attrs["Meta"], "abstract", False)  # not in original snippet
        return super().__new__(mcs, class_name, bases, attrs)


class ModelFactory(Generic[T], DjangoModelFactory, metaclass=BaseFactoryMeta):
    class Meta:
        abstract = True

    @classmethod
    def create(cls, **kwargs) -> T:
        return super().create(**kwargs)

    @classmethod
    def build(cls, **kwargs) -> T:
        return super().build(**kwargs)
