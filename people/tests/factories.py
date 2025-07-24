from typing import TYPE_CHECKING, cast

from factory.declarations import Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation

from users.models import User

if TYPE_CHECKING:
    from people.models import Person


class PersonFactory(DjangoModelFactory['Person']):
    class Meta:
        model = 'people.Person'

    first_name = 'John'
    last_name = 'Frum'
    email = Sequence(lambda i: f'person{i}@example.com')
    organization = SubFactory('actions.tests.factories.OrganizationFactory')
    user: User | None = None  # will be created by Person.save() because it calls Person.create_corresponding_user()

    @post_generation
    def contact_for_actions(self, create, extracted, **kwargs):
        obj = cast('Person', self)
        if create and extracted:
            for action_contact in extracted:
                obj.contact_for_actions.add(action_contact)

    @post_generation
    def general_admin_plans(self, create, extracted, **kwargs):
        obj = cast('Person', self)
        if create and extracted:
            for plan in extracted:
                obj.general_admin_plans.add(plan)
