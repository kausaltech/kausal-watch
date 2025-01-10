from __future__ import annotations

import typing
from dataclasses import asdict, dataclass, field

from actions.models.action import Action
from actions.models.attributes import Attribute

if typing.TYPE_CHECKING:
    from datetime import datetime

    from reversion.models import Version


AttributePath = tuple[int, int, int]


@dataclass
class SerializedVersion:
    type: type
    data: dict
    str: str

    @classmethod
    def from_version(cls, version: Version) -> SerializedVersion:
        return cls(
            type=version.content_type.model_class(),
            data=version.field_dict,
            str=version.object_repr,
        )

    @classmethod
    def from_version_polymorphic(cls, version: Version) -> SerializedVersion:
        model = version.content_type.model_class()
        if issubclass(model, Attribute):
            return SerializedAttributeVersion.from_version(version)
        if issubclass(model, Action):
            return SerializedActionVersion.from_version(version)
        return cls.from_version(version)


@dataclass
class SerializedAttributeVersion(SerializedVersion):
    attribute_path: AttributePath

    @classmethod
    def from_version(cls, version: Version) -> SerializedAttributeVersion:
        base = SerializedVersion.from_version(version)
        assert issubclass(base.type, Attribute)
        attribute_path = (
            version.field_dict['content_type_id'],
            version.field_dict['object_id'],
            version.field_dict['type_id'],
        )
        return cls(
            **asdict(base),
            attribute_path=attribute_path,
        )

@dataclass
class SerializedActionVersion(SerializedVersion):
    completed_at: datetime | None
    completed_by: str | None

    @classmethod
    def from_version(cls, version: Version) -> SerializedActionVersion:
        base = SerializedVersion.from_version(version)
        assert issubclass(base.type, Action)
        completed_at = None
        completed_by = None
        if hasattr(version, 'revision'):
            completed_at = version.revision.date_created
            completed_by = str(version.revision.user) if version.revision.user else ''
        return cls(
            **asdict(base),
            completed_at=completed_at,
            completed_by=completed_by,
        )


@dataclass
class LiveVersions:
    actions: list[Version] = field(default_factory=list)
    related: list[Version] = field(default_factory=list)
