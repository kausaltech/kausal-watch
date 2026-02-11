# Plan Metadata Model

## Overview

This document describes how climate action plans are structured in Kausal Watch, focusing on the metadata model used for classifying and describing actions and indicators. Understanding this model is essential for creating new plans or importing data from external sources.

## Core Entities

### Plan

A **Plan** represents a single climate action plan, typically owned by a city or regional authority. Each plan is associated with:

- A **Client** (the organization that owns the plan in Kausal's system)
- One or more **Organizations** (cities, departments, or other entities responsible for actions)
- **Actions** (the actual climate measures)
- **Indicators** (metrics for tracking progress)
- **CategoryTypes** and **AttributeTypes** (metadata schema, described below)

NOTE: Exactly one CategoryType (that is marked as usable for actions) must be configured as primary action classification. (`Plan.primary_action_classification`)

### Organization

**Organizations** represent the entities responsible for implementing actions. In multi-city plans, each participating city is an Organization. Actions link to their responsible organization via the `primary_org` field.

Organizations form a **tree hierarchy** using django-treebeard's materialized path implementation:

```
Organization: Helsinki (path='00A1', depth=1)
├── Organization: City Executive Office (path='00A10001', depth=2)
│   ├── Organization: Communications Unit (path='00A100010001', depth=3)
│   └── Organization: Legal Affairs (path='00A100010002', depth=3)
└── Organization: Climate Department (path='00A10002', depth=2)
```

**Key fields:**
- `path`: Materialized path string encoding tree position (e.g., "00A10001")
- `depth`: Tree level (1 = root, 2 = child of root, etc.)
- `parent`: Not stored directly - computed from `path` using treebeard

**Tree navigation methods:**
```python
org.get_parent()        # Returns parent organization or None
org.get_ancestors()     # QuerySet of all ancestors (root to parent)
org.get_descendants()   # QuerySet of all children recursively
org.get_children()      # QuerySet of direct children only
```

**Plan Relationships:**

Plans connect to organizations via two mechanisms:

1. **`Plan.organization`** (ForeignKey): The primary organization that owns the plan (typically a city)
2. **`Plan.related_organizations`** (M2M): Additional organizations participating in the plan

The `Organization.objects.available_for_plan(plan)` method returns all organizations accessible for a plan by combining:
- The plan's primary organization and all its descendants
- All related organizations and all their descendants

This filtering includes descendants but **not ancestors**. If child organizations are related to a plan but their parent is not, this creates an "orphaned hierarchy" that may cause validation errors. When adding organizations to a plan, ensure parent organizations are also included if their children are present.

## Classification System

Watch provides two complementary systems for adding metadata to Actions and Indicators:

1. **Categories** (via CategoryTypes) - For classification and filtering
2. **Attributes** (via AttributeTypes) - For structured data fields

### When to Use Categories vs. Attributes

Both systems support filtering actions in the UI. The key distinction is whether **the classification value itself is a concept worth describing**.

| Use **CategoryType** when... | Use **AttributeType** when... |
|------------------------------|-------------------------------|
| Each value is a **concept worth explaining** on its own page | Values are just **labels or measurements** |
| You'd want to show "What is X?" with related actions/indicators | The value only makes sense in context of the action |
| The dimension applies to both actions AND indicators | The dimension only applies to actions OR indicators |
| You want **hierarchical** organization (parent/child) | You need flat choices or data fields |
| Examples: SDGs, Themes, Sectors | Examples: Impact (High/Medium/Low), Budget, Priority |

**The Page Test**: Categories can have associated CMS pages where administrators describe what the category means and add content blocks like "Indicators related to this category" or "Actions contributing to this goal". If that would make sense for your classification, use a CategoryType. If not, use an AttributeType.

**Examples**:

- **"Sustainable Development Goals"** → **CategoryType**. Each SDG (e.g., "SDG 13: Climate Action") is a well-defined concept with official descriptions, targets, and icons. A page showing "What is SDG 13 and which actions contribute to it?" is valuable.

- **"Impact: High/Medium/Low"** → **AttributeType**. These are filtering labels, not concepts. A page titled "What is High?" makes no sense - the value only has meaning attached to a specific action.

- **"Theme: Mobility and Transport"** → **CategoryType**. Users want to browse all mobility actions, and administrators may want to add explanatory content about the city's transport strategy.

- **"Data Source: Wave 1/Wave 2"** → **AttributeType**. This is metadata about where the data came from, useful for filtering but not a concept needing its own page.

## CategoryTypes and Categories

### CategoryType

A **CategoryType** defines a classification dimension for a plan. Each plan can have multiple CategoryTypes.

Key properties:

| Field | Description |
|-------|-------------|
| `identifier` | URL-safe unique identifier (e.g., `theme`, `spatial_frame`) |
| `name` | Human-readable name (e.g., "Theme", "Spatial Frame") |
| `usable_for_actions` | Whether actions can be tagged with this category type |
| `usable_for_indicators` | Whether indicators can be tagged with this category type |
| `select_widget` | `SINGLE` or `MULTIPLE` - controls how many categories can be selected |
| `hide_category_identifiers` | If `True`, category identifiers are hidden in the UI (use when identifiers are auto-generated) |
| `levels` | Optional hierarchy levels (e.g., "Sector" → "Sub-sector") |

### Category

A **Category** is a specific value within a CategoryType. Categories can be hierarchical via the `parent` field.

Key properties:

| Field | Description |
|-------|-------------|
| `identifier` | Unique identifier within the CategoryType |
| `name` | Display name |
| `parent` | Optional parent category (for hierarchical structures) |
| `short_description` | Brief description for UI tooltips |
| `color` | Optional color for visual distinction |

### Example: Hierarchical Theme Categories

```
CategoryType: "Theme" (identifier: theme, single-select)
│
├── Category: "Built environment"
│   ├── Category: "Buildings retrofits" (parent: Built environment)
│   ├── Category: "New construction" (parent: Built environment)
│   └── Category: "Building efficiency" (parent: Built environment)
│
├── Category: "Mobility and transport"
│   ├── Category: "Electric vehicles" (parent: Mobility)
│   ├── Category: "Public transit" (parent: Mobility)
│   └── Category: "Cycling infrastructure" (parent: Mobility)
│
└── Category: "Energy systems"
    ├── Category: "Solar PV" (parent: Energy systems)
    ├── Category: "Wind power" (parent: Energy systems)
    └── Category: "District heating" (parent: Energy systems)
```

### Common CategoryTypes

**CommonCategoryType** and **CommonCategory** are shared classification systems that can be used across multiple plans. Instead of each plan defining its own "UN Sustainable Development Goals" CategoryType, plans can reference the shared SDG taxonomy.

Key benefits:
- **Consistency**: All plans use the same SDG definitions, icons, and descriptions
- **Cross-plan analysis**: Compare actions across different cities using standardized categories
- **Maintenance**: Update SDG metadata once, applies to all plans

Common examples:
- **UN Sustainable Development Goals (SDGs)** - The 17 global goals with official targets and indicators
- **ICLEI Frameworks** - Standardized climate action frameworks
- **Sector classifications** - Common ways to classify urban activities

To use a CommonCategoryType in your plan:
1. Create a CategoryType with `common=<CommonCategoryType instance>`
2. The CategoryType inherits categories from the common type
3. Plan-specific overrides (colors, descriptions) can be added

Plans can mix common category types (like SDGs) with plan-specific ones (like local themes).

### Common CategoryType Patterns

Plans typically include some combination of:

| Pattern | Description | Select Mode |
|---------|-------------|-------------|
| **Primary Theme/Sector** | Main classification (required for most plans) | Single |
| **Secondary Tags** | Cross-cutting themes, detailed tags | Multiple |
| **Geographic Scope** | Where the action applies | Multiple |
| **Responsible Organization** | Who implements (alternative to `primary_org`) | Single |
| **Funding Source** | How it's financed | Multiple |
| **Status/Phase** | Implementation stage (alternative to built-in status) | Single |
| **UN SDGs** | Link to global goals (via CommonCategoryType) | Multiple |

## AttributeTypes and Attributes

### AttributeType

An **AttributeType** defines a custom data field that can be attached to actions or categories.

Key properties:

| Field | Description |
|-------|-------------|
| `identifier` | URL-safe unique identifier |
| `name` | Human-readable field name |
| `format` | Data type (see formats below) |
| `unit` | For numeric attributes, the measurement unit |
| `choice_options` | For choice attributes, the available options |

### Supported Attribute Formats

| Format | Description | Use Case |
|--------|-------------|----------|
| `ORDERED_CHOICE` | Single selection with meaningful order | Priority levels, ratings |
| `UNORDERED_CHOICE` | Single selection, no inherent order | Data source, type classification |
| `OPTIONAL_CHOICE_WITH_TEXT` | Choice + optional text explanation | Status with notes |
| `TEXT` | Plain text field | Contact info, short notes |
| `RICH_TEXT` | HTML/markdown text | Detailed descriptions |
| `NUMERIC` | Decimal number with optional unit | Budget, GHG reduction, area |
| `CATEGORY_CHOICE` | Multi-select from another CategoryType | Complex cross-references |

### Example: Action Attributes

```
AttributeType: "GHG Reduction" (identifier: ghg_reduction, format: NUMERIC)
  - Unit: tCO2eq/year
  - Description: "Estimated annual greenhouse gas reduction"

AttributeType: "Investment Cost" (identifier: investment_cost, format: NUMERIC)
  - Unit: M€
  - Description: "Total investment cost in millions of euros"

AttributeType: "Validation Status" (identifier: validation_status, format: ORDERED_CHOICE)
  - Options: ["Unvalidated", "Validated"]
  - Description: "Whether the action data has been reviewed"

AttributeType: "Data Source" (identifier: data_source, format: UNORDERED_CHOICE)
  - Options: ["CCC AP (W1)", "CCC AP (W2)", "CCC AP (W3)", "CCC AP (W4)"]
  - Description: "Which data collection wave this action came from"
```

## Complete Plan Structure Example

Here's a complete example for a multi-city climate action plan:

```
Client: "NetZeroCities"

Plan: "Climate City Contract Actions"
│
├── Organizations (107 cities)
│   ├── Rome
│   ├── Paris
│   ├── Amsterdam
│   └── ...
│
├── CategoryType: "Emissions Domain" (single-select, primary classification)
│   ├── Adaptation
│   ├── Built environment
│   ├── Circular economy
│   ├── Energy systems
│   ├── Mobility and transport
│   ├── Nature
│   └── ... (11 total)
│
├── CategoryType: "Thematic Tag" (multi-select)
│   ├── Buildings retrofits
│   ├── Electric Vehicles
│   ├── Nature-based solutions
│   └── ... (95 tags)
│
├── CategoryType: "Spatial Frame" (multi-select, 2-level hierarchy)
│   ├── Geographic Scale
│   │   ├── City-wide
│   │   ├── Site-specific
│   │   └── Regional
│   ├── Building Types
│   │   ├── Residential
│   │   └── Municipal
│   └── ...
│
├── AttributeType: "GHG Reduction" (numeric, tCO2eq/year)
├── AttributeType: "Investment Cost" (numeric, M€)
├── AttributeType: "Operational Cost" (numeric, M€/year)
├── AttributeType: "Validation Status" (ordered choice)
├── AttributeType: "GHG Reduction Type" (unordered choice)
└── AttributeType: "Data Source" (unordered choice)

Actions (5000+)
├── Action: "Expand cycling infrastructure"
│   ├── name: "Expand cycling infrastructure"
│   ├── description: "Build 50km of protected bike lanes..."
│   ├── primary_org: Amsterdam
│   ├── categories:
│   │   ├── Emissions Domain: "Mobility and transport"
│   │   ├── Thematic Tags: ["Biking / Cycling", "Policy & Regulatory tools"]
│   │   └── Spatial Frame: ["City-wide", "Streets and Highways"]
│   └── attributes:
│       ├── ghg_reduction: 15000
│       ├── investment_cost: 25.5
│       └── validation_status: "Validated"
└── ...
```

## Design Guidelines

### Action Identifiers

Actions have an `identifier` field that can be either meaningful (e.g., "1.2.3" for hierarchical numbering) or auto-generated. This is controlled by `PlanFeatures.has_action_identifiers`:

- **`has_action_identifiers = True`** (default): The plan uses meaningful identifiers that should be provided during import. Identifiers are shown to users and used for navigation.
- **`has_action_identifiers = False`**: Identifiers are auto-generated UUIDs and hidden from users. Use this when imported data doesn't have a natural identifier scheme.

When importing actions without meaningful identifiers, set this feature flag to `False` and omit the `identifier` field - it will be generated automatically.

### Naming Conventions

- **Identifiers**: Use lowercase with underscores (`emissions_domain`, `ghg_reduction`)
- **Names**: Use title case for CategoryTypes ("Emissions Domain"), sentence case for categories ("Built environment")

### Single vs. Multiple Selection

- Use **single-select** for primary classification (every action should have exactly one)
- Use **multi-select** for tags, scopes, or cross-cutting concerns
- Consider whether "none selected" is a valid state

### Categories vs. Organizations

Both can represent "who is responsible". Use:

- **Organizations** when entities have their own users who log in to update actions
- **Categories** when it's purely for filtering/display and doesn't need user management

### Indicators and Categories

Category types marked with `usable_for_indicators=True` can also classify indicators. This enables:

- Filtering indicators by theme alongside actions
- Showing related indicators when viewing a category
- Consistent taxonomy across the plan
