from django.utils.functional import cached_property
from wagtail.core import blocks

from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryType


class CategoryChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return Category

    @cached_property
    def widget(self):
        from actions.chooser import CategoryChooser
        return CategoryChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class CategoryTypeChooserBlock(blocks.ChooserBlock):
    @cached_property
    def target_model(self):
        return CategoryType

    @cached_property
    def widget(self):
        from actions.chooser import CategoryTypeChooser
        return CategoryTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class AttributeTypeChooserBlock(blocks.ChooserBlock):
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
