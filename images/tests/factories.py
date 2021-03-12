from factory.django import DjangoModelFactory, ImageField
from wagtail_factories import ImageFactory


class AplansImageFactory(ImageFactory):
    class Meta:
        model = 'images.AplansImage'
