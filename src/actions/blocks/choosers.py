from typing import TYPE_CHECKING

from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from kausal_common.datasets.models import DatasetSchema

from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryLevel, CategoryType

if TYPE_CHECKING:
    from actions.chooser import CategoryTypeChooser


class CategoryChooserBlock(blocks.ChooserBlock[Category]):
    class Meta:
        label = _('Category')

    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        from actions.chooser import CategoryChooser

        return CategoryChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class CategoryTypeChooserBlock(blocks.ChooserBlock[CategoryType]):
    class Meta:
        label = _('Category type')

    @cached_property
    def target_model(self) -> type[CategoryType]:
        return CategoryType

    @cached_property
    def widget(self) -> CategoryTypeChooser:
        from actions.chooser import CategoryTypeChooser

        return CategoryTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class CategoryLevelChooserBlock(blocks.ChooserBlock[CategoryLevel]):
    class Meta:
        label = CategoryLevel._meta.verbose_name

    def __init__(self, match: str | None = None, append: str | None = None, **kwargs):
        if match is None:
            match = r'^fields-\d+-value-'
        if append is None:
            append = 'category_type'
        self._match = match
        self._append = append
        super().__init__(**kwargs)

    @cached_property
    def target_model(self) -> type[CategoryLevel]:
        return CategoryLevel

    @cached_property
    def widget(self):
        from actions.chooser import CategoryLevelChooser

        linked_fields = {
            'type': {
                'match': self._match,
                'append': self._append,
            },
        }
        return CategoryLevelChooser(linked_fields=linked_fields)

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class AttributeTypeChooserBlock(blocks.ChooserBlock[AttributeType]):
    class Meta:
        label = _('Field')

    @cached_property
    def target_model(self):
        return AttributeType

    @cached_property
    def widget(self):
        from actions.chooser import AttributeTypeChooser

        return AttributeTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class ActionAttributeTypeChooserBlock(AttributeTypeChooserBlock):
    @cached_property
    def widget(self):
        from actions.chooser import AttributeTypeChooser

        return AttributeTypeChooser(scope='action')


class CategoryAttributeTypeChooserBlock(AttributeTypeChooserBlock):
    # FIXME: Add support for limiting to one CategoryType
    @cached_property
    def widget(self):
        from actions.chooser import AttributeTypeChooser

        return AttributeTypeChooser(scope='category')


class DatasetSchemaChooserBlock(blocks.ChooserBlock[DatasetSchema]):
    class Meta:
        label = _('Dataset Schema')

    @cached_property
    def target_model(self):
        return DatasetSchema

    @cached_property
    def widget(self):
        from actions.chooser import DatasetSchemaChooser

        return DatasetSchemaChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class PlanDatasetSchemaChooserBlock(DatasetSchemaChooserBlock):
    @cached_property
    def widget(self):
        from actions.chooser import DatasetSchemaChooser

        return DatasetSchemaChooser(scope='plan')


class CategoryTypeDatasetSchemaChooserBlock(DatasetSchemaChooserBlock):
    @cached_property
    def widget(self):
        from actions.chooser import DatasetSchemaChooser

        return DatasetSchemaChooser(scope='categorytype')
