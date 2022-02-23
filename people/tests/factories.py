from factory import post_generation, RelatedFactory, SelfAttribute, Sequence, SubFactory
from factory.django import DjangoModelFactory


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = 'people.Person'

    first_name = 'John'
    last_name = 'Frum'
    email = Sequence(lambda i: f'person{i}@example.com')
    organization = SubFactory('actions.tests.factories.OrganizationFactory')
    user = None  # will be created by Person.save() because it calls Person.create_corresponding_user()

    @post_generation
    def contact_for_actions(self, create, extracted, **kwargs):
        if create and extracted:
            for action_contact in extracted:
                self.contact_for_actions.add(action_contact)

    @post_generation
    def general_admin_plans(self, create, extracted, **kwargs):
        if create and extracted:
            for plan in extracted:
                self.general_admin_plans.add(plan)
