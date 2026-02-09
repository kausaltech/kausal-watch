from __future__ import annotations

from pydantic import BaseModel as PydanticBaseModel, ConfigDict


class OperationModel(PydanticBaseModel):
    pass


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
