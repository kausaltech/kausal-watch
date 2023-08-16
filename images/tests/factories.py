from factory.django import DjangoModelFactory, ImageField
from wagtail.test.utils.wagtail_factories import ImageFactory


class AplansImageFactory(ImageFactory):
    class Meta:
        model = 'images.AplansImage'
