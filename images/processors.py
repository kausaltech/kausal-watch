import willow
from wagtail.images.image_operations import FillOperation, ImageTransform
from wagtail.images.rect import Rect


class FocalPointImage:
    def __init__(self, focal_point):
        self.focal_point = focal_point

    def get_focal_point(self):
        if not self.focal_point:
            return
        return Rect(*self.focal_point)


def scale_and_crop(image, size, focal_point=None, crop=None, **kwargs):
    wi = willow.plugins.pillow.PillowImage(image)
    if not isinstance(size, str):
        size = '%dx%d' % size
    if crop is not None:
        crop = ['c%d' % crop]
    else:
        crop = []
    fill_op = FillOperation('fill', size, *crop)
    transform = ImageTransform(image.size)
    transform = fill_op.run(transform, FocalPointImage(focal_point))
    wi = wi.crop(transform.get_rect().round())
    wi = wi.resize(transform.size)
    return wi.image
