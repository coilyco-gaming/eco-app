"""Tests for the AutoGen C# recipe parser (eco-app#242).

Covers:
  - A `RecipeFamily` class folds into the #98 DTO: name, display name, typed and
    tag ingredients, product, byproducts including GarbageOutput, station, skill,
    labor, and craft minutes.
  - All three `CreateCraftTimeValue` shapes Eco emits — named `start:`, a bare
    positional float, and the older three-argument form — read the same value.
    The named form nests `typeof(...)`, which a naive `[^)]*` regex silently
    misses, so this is the regression that matters most.
  - Tag-product variants (`: Recipe` registered via `AddTagProduct`) inherit
    labor, craft time, and skill from their family, and are wired to each other
    as `variants` with the family's own recipe marked default.
  - Skills parse out of `Tech/`, and `[Tag(...)]` membership is collected from
    item classes, not only recipe classes.
  - A malformed class degrades to a warning rather than raising.
  - `index_from_serialized` round-trips the shipped JSON back into a RecipeIndex.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from eco_mcp_app.autogen import build_index_from_autogen
from eco_mcp_app.recipes import index_from_serialized

_FAMILY = """
namespace Eco.Mods.TechTree
{
    [RequiresSkill(typeof(SmeltingSkill), 1)]
    public partial class SmeltCopperRecipe : RecipeFamily
    {
        public SmeltCopperRecipe()
        {
            var recipe = new Recipe();
            recipe.Init(
                name: "SmeltCopper",  //noloc
                displayName: Localizer.DoStr("Smelt Copper"),
                ingredients: new List<IngredientElement>
                {
                    new IngredientElement(typeof(CopperConcentrateItem), 2,typeof(SmeltingSkill)),
                    new IngredientElement("Wood", 4,typeof(SmeltingSkill)), //noloc
                },
                garbages: new List<GarbageOutput>
                {
                    new GarbageOutput(typeof(CeramicScrap), 1.5f),
                },
                items: new List<CraftingElement>
                {
                    new CraftingElement<CopperBarItem>(6),
                    new CraftingElement<SlagItem>(typeof(SmeltingSkill), 2),
                });
            this.Recipes = new List<Recipe> { recipe };
            this.LaborInCalories = CreateLaborInCaloriesValue(60,typeof(SmeltingSkill));
            this.CraftMinutes = CreateCraftTimeValue(
                beneficiary: typeof(SmeltCopperRecipe), start: 6, skillType: typeof(SmeltingSkill));
            CraftingComponent.AddRecipe(tableType: typeof(BloomeryObject), recipeFamily: this);
        }
    }
}
"""

# The bare form, as emitted for simple block recipes, plus no RequiresSkill.
_BARE_CRAFT_TIME = """
namespace Eco.Mods.TechTree
{
    public partial class AdobeRecipe : RecipeFamily
    {
        public AdobeRecipe()
        {
            var recipe = new Recipe();
            recipe.Init(
                name: "Adobe",  //noloc
                displayName: Localizer.DoStr("Adobe"),
                ingredients: new List<IngredientElement>
                {
                    new IngredientElement(typeof(DirtItem), 1,typeof(Skill)),
                },
                garbages: new List<GarbageOutput>
                {
                },
                items: new List<CraftingElement>
                {
                    new CraftingElement<AdobeItem>(4)
                });
            this.LaborInCalories = CreateLaborInCaloriesValue(20);
            this.CraftMinutes = CreateCraftTimeValue(0.16f);
            CraftingComponent.AddRecipe(tableType: typeof(WorkbenchObject), recipeFamily: this);
        }
    }
    [Tag("Constructable")]
    [Tag("Excavatable")]
    public partial class AdobeItem : BlockItem<AdobeBlock>
    {
    }
}
"""

# The older positional form: typeof, UILink, then the value.
_POSITIONAL_CRAFT_TIME = """
namespace Eco.Mods.TechTree
{
    [RequiresSkill(typeof(LoggingSkill), 1)]
    public partial class LegacyRecipe : RecipeFamily
    {
        public LegacyRecipe()
        {
            var recipe = new Recipe();
            recipe.Init(
                name: "Legacy",  //noloc
                displayName: Localizer.DoStr("Legacy"),
                ingredients: new List<IngredientElement>
                {
                    new IngredientElement(typeof(LogItem), 3,typeof(LoggingSkill)),
                },
                items: new List<CraftingElement>
                {
                    new CraftingElement<BoardItem>(1)
                });
            this.LaborInCalories = CreateLaborInCaloriesValue(15);
            this.CraftMinutes = CreateCraftTimeValue(
                typeof(LegacyRecipe), this.UILink(), 2.5f, typeof(LoggingSkill));
            CraftingComponent.AddRecipe(typeof(SawmillObject), this);
        }
    }
}
"""

# A family plus one tag-product variant. The variant declares only ingredients;
# labor, craft time, and skill live on the family.
_TAG_PRODUCT_FAMILY = """
namespace Eco.Mods.TechTree
{
    [RequiresSkill(typeof(CarpentrySkill), 2)]
    public partial class SawBoardsRecipe : RecipeFamily
    {
        public SawBoardsRecipe()
        {
            var recipe = new Recipe();
            recipe.Init(
                name: "SawBoards",  //noloc
                displayName: Localizer.DoStr("Saw Boards"),
                ingredients: new List<IngredientElement>
                {
                    new IngredientElement("Wood", 2,typeof(CarpentrySkill)), //noloc
                },
                items: new List<CraftingElement>
                {
                    new CraftingElement<BoardItem>(3)
                });
            this.LaborInCalories = CreateLaborInCaloriesValue(40,typeof(CarpentrySkill));
            this.CraftMinutes = CreateCraftTimeValue(
                beneficiary: typeof(SawBoardsRecipe),
                start: 1.5f,
                skillType: typeof(CarpentrySkill));
            CraftingComponent.AddRecipe(tableType: typeof(SawmillObject), recipeFamily: this);
        }
    }
    [RequiresSkill(typeof(CarpentrySkill), 1)]
    public partial class SawHardwoodBoardsRecipe : Recipe
    {
        public SawHardwoodBoardsRecipe()
        {
            this.Init(
                name: "SawHardwoodBoards",  //noloc
                displayName: Localizer.DoStr("Saw Hardwood Boards"),
                ingredients: new List<IngredientElement>
                {
                    new IngredientElement("Hardwood", 2,typeof(CarpentrySkill)), //noloc
                },
                items: new List<CraftingElement>
                {
                    new CraftingElement<HardwoodBoardItem>(3)
                });
            CraftingComponent.AddTagProduct(typeof(SawmillObject), typeof(SawBoardsRecipe), this);
        }
    }
}
"""

# A tag-product variant whose family class lives in some file we never read.
_ORPHAN_VARIANT = """
namespace Eco.Mods.TechTree
{
    public partial class StrandedRecipe : Recipe
    {
        public StrandedRecipe()
        {
            this.Init(
                name: "Stranded",  //noloc
                displayName: Localizer.DoStr("Stranded"),
                ingredients: new List<IngredientElement>
                {
                    new IngredientElement("Hardwood", 2,typeof(CarpentrySkill)), //noloc
                },
                items: new List<CraftingElement>
                {
                    new CraftingElement<BoardItem>(3)
                });
            CraftingComponent.AddTagProduct(
                typeof(SawmillObject), typeof(AbsentFamilyRecipe), this);
        }
    }
}
"""

_SKILL = """
namespace Eco.Mods.TechTree
{
    [LocDisplayName("Baking")]
    [RequiresSkill(typeof(ChefSkill), 0), Tag("Chef Specialty"), Tier(3)]
    [Tag("Specialty")]
    public partial class BakingSkill : Skill
    {
        public override int MaxLevel { get { return 7; } }
    }
}
"""


def _tree(tmp_path: Path, files: dict[str, str]) -> Path:
    """Lay out a miniature AutoGen tree on disk."""
    root = tmp_path / "AutoGen"
    for relative, text in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return root


def test_recipe_family_folds_into_the_dto(tmp_path: Path) -> None:
    index = build_index_from_autogen(
        _tree(tmp_path, {"Recipe/SmeltCopper.cs": _FAMILY}), source="test"
    )

    assert index.warnings == []
    (recipe,) = index.recipes
    assert recipe.name == "SmeltCopper"
    assert recipe.display_name == "Smelt Copper"
    assert recipe.product.item == "CopperBarItem"
    assert recipe.product.quantity == 6
    assert recipe.station == "BloomeryObject"
    assert recipe.skill_name == "SmeltingSkill"
    assert recipe.skill_level == 1
    assert recipe.labor_cost == 60
    assert recipe.craft_minutes == 6

    typed, tag = recipe.ingredients
    assert (typed.item, typed.quantity, typed.is_tag) == ("CopperConcentrateItem", 2, False)
    assert (tag.item, tag.quantity, tag.is_tag) == ("Wood", 4, True)

    # The second CraftingElement is a byproduct; GarbageOutput joins it, because a
    # craft that emits slag is not free of it.
    assert [(b.item, b.quantity) for b in recipe.byproducts] == [
        ("SlagItem", 2),
        ("CeramicScrap", 1.5),
    ]


@pytest.mark.parametrize(
    ("source", "name", "expected"),
    [
        (_FAMILY, "SmeltCopper", 6.0),
        (_BARE_CRAFT_TIME, "Adobe", 0.16),
        (_POSITIONAL_CRAFT_TIME, "Legacy", 2.5),
    ],
)
def test_every_craft_time_shape_is_read(
    tmp_path: Path, source: str, name: str, expected: float
) -> None:
    """All three emitted forms must yield the same field.

    The named form nests `typeof(...)` inside the call, so a regex that stops at
    the first `)` reads nothing and reports a free craft.
    """
    index = build_index_from_autogen(_tree(tmp_path, {f"Recipe/{name}.cs": source}), source="test")
    recipe = next(r for r in index.recipes if r.name == name)
    assert recipe.craft_minutes == expected


def test_no_skill_recipe_keeps_a_null_skill(tmp_path: Path) -> None:
    """`typeof(Skill)` is Eco's "no skill required", not a skill named Skill."""
    index = build_index_from_autogen(
        _tree(tmp_path, {"Block/Adobe.cs": _BARE_CRAFT_TIME}), source="test"
    )
    recipe = next(r for r in index.recipes if r.name == "Adobe")
    assert recipe.skill_name is None
    assert recipe.skill_level == 0


def test_tag_product_variants_inherit_family_cost(tmp_path: Path) -> None:
    index = build_index_from_autogen(
        _tree(tmp_path, {"Recipe/SawBoards.cs": _TAG_PRODUCT_FAMILY}), source="test"
    )

    assert index.warnings == []
    head = next(r for r in index.recipes if r.name == "SawBoards")
    variant = next(r for r in index.recipes if r.name == "SawHardwoodBoards")

    # Without inheritance the variant would report a free, instant craft.
    assert variant.labor_cost == head.labor_cost == 40
    assert variant.craft_minutes == head.craft_minutes == 1.5
    assert variant.station == "SawmillObject"
    # The variant declares its own skill level, which must win over the family's.
    assert (variant.skill_name, variant.skill_level) == ("CarpentrySkill", 1)

    assert variant.family == head.family == "SawBoardsRecipe"
    assert head.variants == ["SawHardwoodBoards"]
    assert variant.variants == ["SawBoards"]
    assert head.is_default is True
    assert variant.is_default is False


def test_orphan_variant_warns_instead_of_reporting_a_free_craft(tmp_path: Path) -> None:
    """A variant whose family is missing must say so, not report zero cost."""
    index = build_index_from_autogen(
        _tree(tmp_path, {"Recipe/Orphan.cs": _ORPHAN_VARIANT}), source="test"
    )
    (recipe,) = index.recipes
    assert recipe.labor_cost == 0
    assert any("family class was not parsed" in w for w in index.warnings)


def test_skills_and_tags_are_collected(tmp_path: Path) -> None:
    index = build_index_from_autogen(
        _tree(tmp_path, {"Tech/Baking.cs": _SKILL, "Block/Adobe.cs": _BARE_CRAFT_TIME}),
        source="test",
    )

    (skill,) = index.skills
    assert skill["name"] == "BakingSkill"
    assert skill["displayName"] == "Baking"
    assert skill["maxLevel"] == 7
    assert skill["tier"] == 3
    assert skill["profession"] == "ChefSkill"

    # Tags live on the item class, which is not a recipe class — the collector has
    # to look at every class, or tag ingredients become unresolvable.
    assert index.tags["Constructable"] == ["AdobeItem"]
    assert index.tags["Excavatable"] == ["AdobeItem"]


def test_lookup_maps_are_built(tmp_path: Path) -> None:
    index = build_index_from_autogen(
        _tree(tmp_path, {"Recipe/SmeltCopper.cs": _FAMILY, "Recipe/Adobe.cs": _BARE_CRAFT_TIME}),
        source="test",
    )
    assert index.by_product["CopperBarItem"] == ["SmeltCopper"]
    assert index.by_station["BloomeryObject"] == ["SmeltCopper"]
    assert index.by_skill["SmeltingSkill"] == ["SmeltCopper"]
    assert index.counts()["recipes"] == 2


def test_class_without_init_is_skipped_quietly(tmp_path: Path) -> None:
    """Template scaffolding with no Init is not a recipe and must not warn."""
    source = """
namespace Eco.Mods.TechTree
{
    public partial class EmptyRecipe : RecipeFamily
    {
        public EmptyRecipe() { }
    }
}
"""
    index = build_index_from_autogen(_tree(tmp_path, {"Recipe/Empty.cs": source}), source="test")
    assert index.recipes == []
    assert index.warnings == []


def test_missing_root_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        build_index_from_autogen(tmp_path / "nope", source="test")


def test_serialized_round_trip(tmp_path: Path) -> None:
    """The shipped JSON rehydrates into an equivalent index."""
    original = build_index_from_autogen(
        _tree(tmp_path, {"Recipe/SawBoards.cs": _TAG_PRODUCT_FAMILY, "Tech/Baking.cs": _SKILL}),
        source="test",
    )
    restored = index_from_serialized(original.to_dict())

    assert restored.to_dict() == original.to_dict()
    assert restored.counts() == original.counts()
