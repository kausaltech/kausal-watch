# Review: `test_attribute_type_choice_option_deletion.py`

## Evaluation Against Project Test Conventions

Conventions are defined in `docs/unit-tests.md` and `CLAUDE.md`.

### Key Convention Summary

1. **Use registered singleton fixtures** (`action`, `plan`, `action_attribute_type__ordered_choice`) when
   you need exactly one instance with default values.
2. **Use `Factory.create()`** when you need to customize the instance or create multiple instances.
3. **Avoid `_factory()` call style** — the docs say: *"Avoid using factory-as-function (`action_factory()`)
   unless the factory has customizations in the registration. Since type hints require importing the Factory
   class anyway, prefer `ActionFactory.create()` for clarity and type safety."*

### Issues Found

#### 1. Custom fixtures duplicate registered ones (high severity)

The test file defines four fixtures (lines 69–106) that duplicate fixtures already registered
via `pytest-factoryboy` in the root `conftest.py`:

| Test file fixture                              | Registered equivalent                    |
|------------------------------------------------|------------------------------------------|
| `action_attribute_type_ordered_choice`         | `action_attribute_type__ordered_choice`   |
| `action_attribute_type_optional_choice_with_text` | `action_attribute_type__optional_choice` |
| `choice_option`                                | `attribute_type_choice_option`            |
| `choice_option_with_text`                      | `attribute_type_choice_option__optional`  |

**Note:** `OPTIONAL_CHOICE_WITH_TEXT` has DB value `'optional_choice'`, so the registered fixture
name is `action_attribute_type__optional_choice`.

The registered fixtures are created in `conftest.py` lines 306–328 (attribute types for every
`AttributeFormat` value) and lines 321–328 (choice option convenience fixtures).

#### 2. Missing type annotations on fixture and test parameters (medium severity)

Per the testing guide, all fixture and test function parameters should have type annotations:

```python
# Current (missing annotations):
def test_deleting_choice_option_cascades_to_attribute_choice(
    self,
    action_with_choice_attribute,
    choice_option,
):

# Should be:
def test_deleting_choice_option_cascades_to_attribute_choice(
    self,
    action_with_choice_attribute: Action,
    attribute_type_choice_option: AttributeTypeChoiceOption,
):
```

This applies to essentially all fixture parameters throughout the file.

#### 3. Repeated inline import of `AttributeTypeWrapper` (low severity)

The import `from actions.attributes import AttributeType as AttributeTypeWrapper` appears
inline in 6 different test methods. This should be a module-level import.

#### 4. `ActionFactory.create(plan=plan)` where `action` fixture would suffice (low severity)

A few single-action fixture cases create actions explicitly when the registered `action`
fixture could be used instead. However, in many tests multiple or customized actions are
needed, so direct `Factory.create()` calls are appropriate per the guidelines.

#### 5. `ReportFactory` / `ReportTypeFactory` used via direct `.create()` — correct

These factories are **not registered** as pytest-factoryboy fixtures. Using them via
direct `Factory.create()` calls is the correct approach.

#### 6. Direct `AttributeTypeFactory.create()` for customized instances — correct

Tests in `TestDeserializationWarnings` and `TestEdgeCases` that need attribute types with
specific properties use `AttributeTypeFactory.create(...)` directly. This follows the
"use Factory.create() when you need to customize" guideline.
