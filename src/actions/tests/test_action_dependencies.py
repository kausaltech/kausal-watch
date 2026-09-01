import pytest

pytestmark = pytest.mark.django_db


# FIXME: Tests commented out because we disabled `ActionDependencyRelationship.clean()` for now.
# def test_action_dependency_clean_valid_relationship(plan, action_factory):
#     action1 = action_factory(plan=plan)
#     action2 = action_factory(plan=plan)
#     relationship = ActionDependencyRelationship(preceding=action1, dependent=action2)
#     relationship.clean()  # Should not raise any exception
#
#
# def test_action_dependency_clean_missing_actions(plan):
#     relationship = ActionDependencyRelationship()
#     with pytest.raises(ValidationError):
#         relationship.clean()
#
#
# def test_action_dependency_clean_different_plans(plan, plan_factory, action_factory):
#     action1 = action_factory(plan=plan)
#     action2 = action_factory(plan=plan)
#     other_plan = plan_factory(name="Other Plan")
#     action3 = action_factory(plan=other_plan)
#     relationship = ActionDependencyRelationship(preceding=action1, dependent=action3)
#     with pytest.raises(ValidationError) as excinfo:
#         relationship.clean()
#     assert "The preceding and dependent actions must belong to the same plan." in str(excinfo.value)
#
# def test_action_dependency_clean_different_role_plan(plan, plan_factory, action_factory):
#     action1 = action_factory(plan=plan)
#     action2 = action_factory(plan=plan)
#     other_plan = plan_factory(name="Other Plan")
#     role = ActionDependencyRole.objects.create(plan=other_plan, name="Test Role")
#     relationship = ActionDependencyRelationship(preceding=action1, dependent=action2, preceding_role=role)
#     with pytest.raises(ValidationError) as excinfo:
#         relationship.clean()
#     assert "The preceding action role must belong to the same plan as the actions." in str(excinfo.value)
#
#
# def test_action_dependency_clean_cycle_detection(plan, action_factory):
#     action1 = action_factory(plan=plan)
#     action2 = action_factory(plan=plan)
#     action3 = action_factory(plan=plan)
#     ActionDependencyRelationship.objects.create(preceding=action1, dependent=action2)
#     ActionDependencyRelationship.objects.create(preceding=action2, dependent=action3)
#     relationship = ActionDependencyRelationship(preceding=action3, dependent=action1)
#     with pytest.raises(ValidationError) as excinfo:
#         relationship.clean()
#     assert "The dependency relationships contain a cycle." in str(excinfo.value)
#
#
# def test_action_dependency_max_chain_length(plan, action_factory):
#     # Let's create several chained actions more than the allowed chain length
#     action1 = action_factory(plan=plan)
#     action2 = action_factory(plan=plan)
#     action3 = action_factory(plan=plan)
#     action4 = action_factory(plan=plan)
#
#     ActionDependencyRelationship.objects.create(preceding=action1, dependent=action2).clean()
#     ActionDependencyRelationship.objects.create(preceding=action2, dependent=action3).clean()
#     relationship = ActionDependencyRelationship(preceding=action3, dependent=action4)
#     with pytest.raises(ValidationError) as excinfo:
#         relationship.clean()
#
#     assert "Maximum dependency chain length exceeded." in str(excinfo.value)
