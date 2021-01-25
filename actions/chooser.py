from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin
from generic_chooser.widgets import AdminChooser
from django.utils.translation import gettext_lazy as _
from wagtail.search.backends import get_search_backend
from wagtail.core import hooks

from .models import Category


class CategoryChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        plan = self.request.user.get_active_admin_plan()
        objects = Category.objects.filter(type__plan=plan).distinct()
        return objects

    def get_object_list(self, search_term=None, **kwargs):
        objs = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            objs = search_backend.autocomplete(search_term, objs)

        return objs


class CategoryChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = CategoryChooserMixin

    icon = 'user'
    model = Category
    page_title = _("Choose a category")
    per_page = 30
    fields = ['identifier', 'name']


class CategoryChooser(AdminChooser):
    choose_one_text = _('Choose a category')
    choose_another_text = _('Choose another category')
    model = Category
    choose_modal_url_name = 'category_chooser:choose'


@hooks.register('register_admin_viewset')
def register_category_chooser_viewset():
    return CategoryChooserViewSet('category_chooser', url_prefix='category-chooser')
