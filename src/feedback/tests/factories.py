from factory import SubFactory
from factory.django import DjangoModelFactory

from actions.models import Plan
from actions.tests.factories import PlanFactory
from feedback.models import UserFeedback


class UserFeedbackFactory(DjangoModelFactory[UserFeedback]):
    class Meta:
        model = 'feedback.UserFeedback'

    plan = SubFactory[UserFeedback, Plan](PlanFactory)
    name = 'John Frum'
    email = 'john.frum@example.com'
    comment = 'This is great!'
    url = 'https://example.com/feedback'
