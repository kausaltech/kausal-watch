from wagtail.test.utils.wagtail_factories import ImageFactory

from factory.django import DjangoModelFactory, ImageField


class AplansImageFactory(ImageFactory):
    class Meta:
        model = 'images.AplansImage'
