from __future__ import annotations

from xlsxwriter.workbook import Worksheet
from xlsxwriter.format import Format

from typing import Any

import typing
if typing.TYPE_CHECKING:
    from reports.spreadsheets.excel_report import ExcelFormats


class CursorWriter:
    def __init__(
            self,
            worksheet: Worksheet,
            formats: ExcelFormats | None = None,
            default_format: Format | None = None,
            start: tuple[int, int] = (0, 0),
            width: int | None = None,
            merge: bool =False
    ):
        self.default_format = default_format
        self.worksheet = worksheet
        self.cursor = start
        self.start = start
        if width:
            self.fill_to = start[1] + width
        else:
            self.fill_to = -1
        self.width = width
        self.current_format = None
        self.formats = formats
        self.merge = merge

    def write(self, value: Any, format: Format | None = None, url: str | None = None) -> CursorWriter:
        format = format if format else self.default_format
        self.current_format = format
        x, y = self.cursor
        if url:
            self.worksheet.write_url(x, y, url, format, string=value)
        else:
            self.worksheet.write(x, y, value, format)
        self.cursor = (x, y + 1)
        return self

    def write_empty(self, count: int) -> CursorWriter:
        while count > 0:
            self.write('', format=self.current_format)
            count -= 1
        return self

    def newline(self) -> CursorWriter:
        x, y = self.cursor
        y_delta = self.fill_to - y
        if y_delta > 0:
            self.write_empty(y_delta)
        self.cursor = (x + 1, self.start[1])
        return self

    def write_cells(self, cells: Sequence[list[tuple[str, str]|tuple[str, str, str]]]) -> None:
        for row in cells:
            extra_padding_all_cells = extra_padding_last_cell_only = 0

            if self.merge and self.width:
                # Add the appropriate amount of empty cells
                # if we are fitting a row within a specified width (measured in cell counts)
                row_length = len(row)
                if row_length > 0 and row_length < self.width:
                    extra_padding_all_cells = int(self.width / row_length) - 1
                    extra_padding_last_cell_only = self.width % row_length

            for i, cell in enumerate(row):
                format: Format | None = None
                format_or_key: Format | str | None = cell[1] if len(cell) > 1 else None
                if isinstance(format_or_key, str):
                    format = getattr(self.formats, format_or_key, None)
                else:
                    format = format_or_key
                url = None
                if len(cell) > 3:
                    raise ValueError('Invalid cell tuple')
                if len(cell) == 3:
                    url = cell[2]

                start_cursor = self.cursor
                self.write(cell[0], format=format, url=url)

                add_empty = extra_padding_all_cells
                if i + 1 == len(row):
                    add_empty += extra_padding_last_cell_only
                if add_empty > 0:
                    self.write_empty(add_empty)
                    end_cursor = self.cursor
                    self.worksheet.merge_range(start_cursor[0], start_cursor[1], end_cursor[0], end_cursor[1] - 1, cell[0], format)
            self.newline()
