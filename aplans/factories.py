# https://github.com/FactoryBoy/factory_boy/issues/468#issuecomment-1536373442
from __future__ import annotations

from typing import get_args

from django.db.models.base import Model

from factory.base import FactoryMetaClass
from factory.django import DjangoModelFactory


class BaseFactoryMeta(FactoryMetaClass):
    def __new__(mcs, class_name, bases: list[type], attrs):
        orig_bases = attrs.get("__orig_bases__", [])
        for t in orig_bases:
            if t.__name__ == "ModelFactory" and t.__module__ == __name__:
                type_args = get_args(t)
                if len(type_args) == 1:
                    if "Meta" not in attrs:
                        attrs["Meta"] = type("Meta", (), {})
                    attrs["Meta"].model = type_args[0]
                    attrs["Meta"].abstract = False  # not in original snippet
        return super().__new__(mcs, class_name, bases, attrs)


class ModelFactory[T: Model](DjangoModelFactory[T], metaclass=BaseFactoryMeta):
    class Meta:
        abstract = True
