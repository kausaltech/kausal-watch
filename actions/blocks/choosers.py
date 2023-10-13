from django.utils.functional import cached_property
from django.utils.translation import gettext_lazy as _
from wagtail import blocks

from actions.models.attributes import AttributeType
from actions.models.category import Category, CategoryLevel, CategoryType


class CategoryChooserBlock(blocks.ChooserBlock):
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


class CategoryTypeChooserBlock(blocks.ChooserBlock):
    class Meta:
        label = _('Category type')

    @cached_property
    def target_model(self):
        return CategoryType

    @cached_property
    def widget(self):
        from actions.chooser import CategoryTypeChooser
        return CategoryTypeChooser()

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class CategoryLevelChooserBlock(blocks.ChooserBlock):
    class Meta:
        label = CategoryLevel._meta.verbose_name

    @cached_property
    def target_model(self):
        return CategoryLevel

    @cached_property
    def widget(self):
        from actions.chooser import CategoryLevelChooser
        linked_fields = {
            'type': {
                'match': r'^fields-\d+-value-',
                'append': 'category_type'
            }
        }
        return CategoryLevelChooser(linked_fields=linked_fields)

    def get_form_state(self, value):
        return self.widget.get_value_data(value)


class AttributeTypeChooserBlock(blocks.ChooserBlock):
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
