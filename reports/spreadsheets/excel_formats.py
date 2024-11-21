from __future__ import annotations

import inspect
import typing

from reports.report_formatters import ActionReportContentField

if typing.TYPE_CHECKING:
    from wagtail.blocks import BoundBlock

    import xlsxwriter
    from xlsxwriter.format import Format


class ExcelFormats(dict):
    workbook: xlsxwriter.Workbook
    _formats_for_fields: dict

    def __init__(self, workbook, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workbook = workbook
        self._formats_for_fields = dict()
        self._initialize_styles()

    def _initialize_styles(self) -> None:
        for name, callback in inspect.getmembers(self.StyleSpecifications, inspect.ismethod):
            _format = self.workbook.add_format()
            self[name] = _format
            callback(_format)

    class StyleSpecifications:
        BG_COLOR_ODD = '#f4f4f4'
        BG_COLOR_HEADER = '#0a5e43'
        COLOR_WHITE = '#ffffff'
        COLOR_LIGHT_HEADER = '#f0f0f0'
        COLOR_PAGE_HEADER = '#3c504a'

        @classmethod
        def header_row(cls, f: Format) -> None:
            f.set_font_color('#ffffff')
            f.set_bg_color(cls.BG_COLOR_HEADER)
            f.set_bold()

        @classmethod
        def date(cls, f: Format) -> None:
            f.set_num_format('d mmmm yyyy')
            f.set_align('left')
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def timestamp(cls, f: Format) -> None:
            cls.date(f)
            f.set_num_format('d mmmm yyyy hh:mm')

        @classmethod
        def odd_row(cls, f: Format) -> None:
            f.set_bg_color(cls.BG_COLOR_ODD)

        @classmethod
        def even_row(cls, f: Format) -> None:
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def title(cls, f: Format) -> None:
            f.set_bold()
            f.set_font_size(24)
            cls.header_row(f)

        @classmethod
        def sub_title(cls, f: Format) -> None:
            f.set_bold()
            f.set_font_size(18)
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def metadata_label(cls, f: Format) -> None:
            f.set_bold()
            f.set_align('right')
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def metadata_value(cls, f: Format) -> None:
            f.set_align('left')
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def sub_sub_title(cls, f: Format) -> None:
            f.set_font_size(16)
            f.set_bg_color(cls.COLOR_WHITE)

        @classmethod
        def all_rows(cls, f: Format) -> None:
            f.set_border(0)
            f.set_align('top')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_value(cls, f: Format) -> None:
            f.set_font_size(8)
            f.set_left()
            f.set_bottom()
            f.set_right()
            f.set_align('vjustify')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_label(cls, f: Format) -> None:
            f.set_bg_color(cls.COLOR_LIGHT_HEADER)
            f.set_font_size(8)
            f.set_left()
            f.set_top()
            f.set_right()
            f.set_align('vjustify')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_page_header(cls, f: Format) -> None:
            f.set_bg_color(cls.COLOR_PAGE_HEADER)
            f.set_color('#ffffff')
            f.set_align('top')
            f.set_font_size(10)
            f.set_bold()
            f.set_align('vjustify')
            f.set_text_wrap(True)

        @classmethod
        def action_digest_value_long(cls, f: Format) -> None:
            cls.action_digest_value(f)
            f.set_bold(False)
            f.set_font_size(8)
            f.set_align('top')
            f.set_align('vjustify')
            f.set_text_wrap(True)

    def __getattr__(self, name):
        return self[name]


    def set_for_field(self, field: BoundBlock, labels: list) -> None:
        if None not in {self._formats_for_fields.get(label) for label in labels}:
            return
        block: ActionReportContentField = typing.cast(ActionReportContentField, field.block)
        cell_format_specs: dict[str, str] | None = block.get_xlsx_cell_format(field.value)
        cell_format = self.workbook.add_format(cell_format_specs)
        self.StyleSpecifications.all_rows(cell_format)
        for label in labels:
            self._formats_for_fields[label] = cell_format

    def set_for_label(self, label: str, xlsx_format: Format) -> None:
        cell_format = self._formats_for_fields.get(label)
        if not cell_format:
            self._formats_for_fields[label] = xlsx_format

    def get_for_label(self, label):
        return self._formats_for_fields.get(label)
