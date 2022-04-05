from django.db import models
from django.utils.translation import gettext_lazy as _
from modelcluster.models import ClusterableModel

from aplans.utils import IdentifierField, OrderedModel


class AttributeType(ClusterableModel, OrderedModel):
    class AttributeFormat(models.TextChoices):
        ORDERED_CHOICE = 'ordered_choice', _('Ordered choice')
        OPTIONAL_CHOICE_WITH_TEXT = 'optional_choice', _('Optional choice with optional text')
        RICH_TEXT = 'rich_text', _('Rich text')
        NUMERIC = 'numeric', _('Numeric')

    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))
    format = models.CharField(max_length=50, choices=AttributeFormat.choices, verbose_name=_('Format'))

    public_fields = [
        'identifier', 'name', 'format', 'choice_options'
    ]

    # Be sure to inherit from this Meta class in subclasses (just in case we later add something here that should be
    # inherited)!
    class Meta:
        abstract = True

    def __str__(self):
        return self.name


class AttributeTypeChoiceOption(ClusterableModel, OrderedModel):
    identifier = IdentifierField()
    name = models.CharField(max_length=100, verbose_name=_('name'))

    # Subclasses of this must have a ParentalKey called `type` to a subclass of AttributeType with reverse accessor
    # `choice_options`. Example:
    # type = ParentalKey(CategoryAttributeType, on_delete=models.CASCADE, related_name='choice_options')

    public_fields = [
        'identifier', 'name'
    ]

    # Be sure to inherit from this Meta class in subclasses!
    class Meta:
        unique_together = (('type', 'identifier'), ('type', 'order'),)
        ordering = ('type', 'order')
        abstract = True

    def __str__(self):
        return self.name
