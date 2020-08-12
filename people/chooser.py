from generic_chooser.views import ModelChooserViewSet, ModelChooserMixin
from generic_chooser.widgets import AdminChooser
from django.utils.translation import gettext_lazy as _
from wagtail.search.backends import get_search_backend
from wagtail.core import hooks

from .models import Person


class PersonChooserMixin(ModelChooserMixin):
    def get_unfiltered_object_list(self):
        objects = self.model.objects.all()
        if self.order_by:
            objects = objects.order_by('last_name', 'first_name')
        return objects

    def get_object_list(self, search_term=None, **kwargs):
        object_list = self.get_unfiltered_object_list()

        if search_term:
            search_backend = get_search_backend()
            object_list = search_backend.autocomplete(search_term, object_list)

        return object_list

    def get_row_data(self, item):
        avatar_url = item.get_avatar_url(self.request, '50x50')
        return {
            'choose_url': self.get_chosen_url(item),
            'name': self.get_object_string(item),
            'title': item.title,
            'avatar_url': avatar_url,
        }

    def get_results_template(self):
        return 'people/chooser_results.html'


class PersonChooserViewSet(ModelChooserViewSet):
    chooser_mixin_class = PersonChooserMixin
    icon = 'user'
    model = Person
    page_title = _("Choose person")
    per_page = 10
    order_by = ('last_name', 'first_name')
    fields = ['first_name', 'last_name', 'email']


class PersonChooser(AdminChooser):
    choose_one_text = _('Choose a person')
    choose_another_text = _('Choose another person')
    link_to_chosen_text = _('Edit this person')
    model = Person
    choose_modal_url_name = 'person_chooser:choose'


@hooks.register('register_admin_viewset')
def register_person_chooser_viewset():
    return PersonChooserViewSet('person_chooser', url_prefix='person-chooser')
