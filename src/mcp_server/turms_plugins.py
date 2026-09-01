from __future__ import annotations

from turms.stylers.base import BaseStyler, StylerConfig  # pyright: ignore[reportMissingTypeStubs]


class RenamerStylerConfig(StylerConfig):
    type: str = 'mcp_server.turms_plugins.RenamerStyler'


class RenamerStyler(BaseStyler):
    def style_fragment_name(self, name: str) -> str:
        return name

    def style_object_name(self, name: str) -> str:
        return name

    def style_input_name(self, name: str) -> str:
        return name

    def style_query_name(self, name: str) -> str:
        name = name.removeprefix('MCP')
        return name

    def style_mutation_name(self, name: str) -> str:
        name = name.removeprefix('MCP')
        return name
