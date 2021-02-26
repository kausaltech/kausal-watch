from factory import post_generation, RelatedFactory, Sequence, SubFactory
from factory.django import DjangoModelFactory


class PersonFactory(DjangoModelFactory):
    class Meta:
        model = 'people.Person'

    first_name = 'John'
    last_name = 'Frum'
    email = Sequence(lambda i: f'person{i}@example.com')
    organization = SubFactory('actions.tests.factories.OrganizationFactory')
    user = SubFactory('users.tests.factories.UserFactory')

    # contact_for_actions = RelatedFactory('actions.tests.factories.ActionContactPersonFactory',
    #                                      factory_related_name='person')
    @post_generation
    def contact_for_actions(self, create, extracted, **kwargs):
        if not create:
            return

        if extracted:
            for action in extracted:
                self.contact_for_actions.add(action)
