from factory import SubFactory
from factory.django import DjangoModelFactory

from actions.tests.factories import PlanFactory


class UserFeedbackFactory(DjangoModelFactory):
    class Meta:
        model = 'feedback.UserFeedback'

    plan = SubFactory(PlanFactory)
    name = 'John Frum'
    email = 'john.frum@example.com'
    comment = "This is great!"
    url = 'https://example.com/feedback'
