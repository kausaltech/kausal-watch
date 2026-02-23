from typing import TYPE_CHECKING

from factory.declarations import Sequence, SubFactory
from factory.django import DjangoModelFactory
from factory.helpers import post_generation

if TYPE_CHECKING:
    from actions.models import Action, Plan
    from people.models import Person
    from users.models import User


class PersonFactory(DjangoModelFactory['Person']):
    class Meta:
        model = 'people.Person'
        skip_postgeneration_save = True

    first_name = 'John'
    last_name = 'Frum'
    email = Sequence(lambda i: f'person{i}@example.com')
    organization = SubFactory('actions.tests.factories.OrganizationFactory')
    user: User | None = None  # will be created by Person.save() because it calls Person.create_corresponding_user()

    @post_generation
    @staticmethod
    def contact_for_actions(obj: Person, create: bool, extracted: list[Action]) -> None:
        if create and extracted:
            for action_contact in extracted:
                obj.contact_for_actions.add(action_contact)
            obj.save()

    @post_generation
    @staticmethod
    def general_admin_plans(obj: Person, create: bool, extracted: list[Plan]) -> None:
        if create and extracted:
            for plan in extracted:
                obj.general_admin_plans.add(plan)
            obj.save()
