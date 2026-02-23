from __future__ import annotations

from typing import ClassVar, Protocol

from pydantic import BaseModel as PydanticBaseModel, ConfigDict


class ObjectBaseModel(PydanticBaseModel):
    pass


class OperationMeta(Protocol):
    document: str

class QueryModel(PydanticBaseModel):
    Arguments: ClassVar[type[ArgumentsModel]]
    Meta: ClassVar[type[OperationMeta]]


class MutationModel(PydanticBaseModel):
    Arguments: ClassVar[type[ArgumentsModel]]
    Meta: ClassVar[type[OperationMeta]]


type OperationModel = QueryModel | MutationModel


class InputTypeModel(PydanticBaseModel):
    pass


class ArgumentsModel(PydanticBaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        validate_assignment=True,
        validate_by_alias=True,
        validate_by_name=True,
        arbitrary_types_allowed=True,
        protected_namespaces=(),
    )
