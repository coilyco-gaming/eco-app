"""Parse Eco's generated `Mods/__core__/AutoGen` C# into a `RecipeIndex`.

`recipes.py` seeded the bill-of-materials layer from Eco Gnome's export because
that was the only machine-readable recipe graph available (eco-app#98, #105).
This module reads the graph Eco itself ships: the `AutoGen` tree inside the
dedicated server, which is plain C# emitted from `RecipeTemplate.tt` and friends.

Why this source wins (eco-app#242):

* It is the **only** vanilla source carrying every DTO field at once. Eco Gnome's
  export lacks a crafting-table tier and is pinned to whatever the upstream
  bundled; `Eco.ReferenceAssemblies` is metadata-only — its method bodies are all
  `ldnull; throw`, which drops ingredients, products, labor, craft time, and the
  crafting station for 94% of recipes.
* It needs no credential. The dedicated server is `steamcmd +login anonymous
  +app_update 739590`, confirmed by SLG on the official forum — owning the game
  is not a gate.
* It is versioned with the server we actually run.

Parsing rather than compiling: the tree is machine-generated from templates, so
its grammar is a handful of stable shapes rather than the whole C# language. A
regex reader keeps this a build step with no .NET in the pipeline. `autogen.py`
never runs at request time — `scripts/autogen_refresh.py` writes the parsed index
to `data/eco_autogen_data.json`, and that vendored file is what ships, matching
the "vendor, do not fetch at build time" finding from eco-app#105.

Two class shapes carry recipes, and both are handled:

1. ``class XRecipe : RecipeFamily`` — the common form. Declares one inner
   ``new Recipe()``, ``LaborInCalories``, ``CraftMinutes``, and registers with
   ``CraftingComponent.AddRecipe(tableType: typeof(SomeObject), ...)``.
2. ``class XRecipe : Recipe`` — a *tag product* variant, e.g. `SawHardwoodBoards`
   and `SawSoftwoodBoards` both satisfying `SawBoardsRecipe`. It calls
   ``this.Init(...)`` directly and registers with
   ``CraftingComponent.AddTagProduct(typeof(Station), typeof(FamilyRecipe), this)``.
   The second `typeof` is the family, which is what populates `Recipe.family` and
   lets sibling variants find each other.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .crafting import prettify_eco_name
from .recipes import Recipe, RecipeComponent, RecipeIndex

# Where a parsed index came from, surfaced on the payload so a consumer can tell
# an AutoGen-derived graph from the Eco Gnome seed. `scripts/autogen_refresh.py`
# substitutes the real Steam build id for `<buildid>`.
AUTOGEN_SOURCE_TEMPLATE = "Eco dedicated server AutoGen (Steam app 739590, build {build_id})"

# Directories under AutoGen that are pure world/lore data with no recipe, skill,
# or tag content. Skipping them keeps the walk honest about what it read rather
# than silently scanning 2,000 files to find nothing.
_SKIP_DIRS = frozenset({"BlockFills", "BlockFormGroup", "BlockFormType", "Forms", "Rubble"})

# Every class, not just recipe ones: `[Tag("Wood")]` sits on item and block
# classes, and the tag -> members map is what lets a tag ingredient be expanded.
# The base type is captured so the fold can dispatch on it.
_CLASS_RE = re.compile(r"public\s+(?:partial\s+)?class\s+(?P<name>\w+)\s*:\s*(?P<base>\w+)")
# Attributes sit above the class declaration; capture the whole run so a class's
# own attributes are not confused with the previous class's.
# Attributes are matched without their opening bracket: the generator freely
# combines them on one line — `[RequiresSkill(typeof(ChefSkill), 0), Tag("Chef
# Specialty"), Tier(3)]` — so anchoring on `[` silently drops every attribute
# after the first. A `\b` prefix still keeps `Tier` from matching `BlockTier`.
_REQUIRES_SKILL_RE = re.compile(r"\bRequiresSkill\(typeof\((?P<skill>\w+)\)\s*,\s*(?P<level>\d+)\)")
_LOC_DISPLAY_RE = re.compile(r'\bLocDisplayName\("(?P<value>[^"]*)"\)')
_TIER_RE = re.compile(r"\bTier\((?P<value>\d+)\)")
_TAG_RE = re.compile(r'\bTag\("(?P<value>[^"]+)"')
_MAX_LEVEL_RE = re.compile(r"MaxLevel\s*\{\s*get\s*\{\s*return\s+(?P<value>\d+)\s*;")

_INIT_NAME_RE = re.compile(r'name:\s*"(?P<value>[^"]*)"')
_INIT_DISPLAY_RE = re.compile(r'displayName:\s*Localizer\.DoStr\("(?P<value>[^"]*)"\)')
# `Initialize(displayText: Localizer.DoStr("Smelt Copper"), ...)` is the fallback
# display name for families whose inner Recipe omitted one.
_INITIALIZE_DISPLAY_RE = re.compile(r'Initialize\(\s*displayText:\s*Localizer\.DoStr\("([^"]*)"\)')

_INGREDIENT_RE = re.compile(
    r"new\s+IngredientElement\(\s*(?:typeof\((?P<type>\w+)\)|\"(?P<tag>[^\"]+)\")\s*,\s*"
    r"(?P<qty>[0-9.]+)f?"
)
_PRODUCT_RE = re.compile(
    r"new\s+CraftingElement<(?P<item>\w+)>\(\s*(?:typeof\(\w+\)\s*,\s*)?(?P<qty>[0-9.]*)f?\s*\)"
)
_GARBAGE_RE = re.compile(
    r"new\s+GarbageOutput\(\s*typeof\((?P<item>\w+)\)\s*,\s*(?P<qty>[0-9.]+)f?"
)

_LABOR_RE = re.compile(r"CreateLaborInCaloriesValue\(\s*(?P<value>[0-9.]+)f?")
# Inside a CreateCraftTimeValue call, the 0.13 named form is `start: 6`. The other
# two shapes are positional and handled by reading the argument list.
_CRAFT_MINUTES_NAMED_RE = re.compile(r"\bstart:\s*(?P<value>[0-9.]+)f?")
_NUMBER_RE = re.compile(r"[0-9]+(?:\.[0-9]+)?f?")
_ADD_RECIPE_RE = re.compile(
    r"CraftingComponent\.AddRecipe\(\s*(?:tableType:\s*)?typeof\((?P<station>\w+)\)"
)
_ADD_TAG_PRODUCT_RE = re.compile(
    r"CraftingComponent\.AddTagProduct\(\s*typeof\((?P<station>\w+)\)\s*,\s*"
    r"typeof\((?P<family>\w+)\)"
)


def _number(raw: str, default: float = 0.0) -> float:
    """Read an Eco literal (`2`, `1.5f`, or an empty default-argument slot)."""
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


def _call_arguments(text: str, function: str) -> str | None:
    """Return the argument text of `function(...)`, respecting nested parentheses.

    The generated calls nest freely — `CreateCraftTimeValue(beneficiary:
    typeof(SmeltCopperRecipe), start: 6, ...)` — so a `[^)]*` regex stops at the
    first inner `typeof(...)` and silently reads nothing. Scanning for the
    matching close paren is the only way to get the whole argument list.
    """
    start = text.find(f"{function}(")
    if start < 0:
        return None
    cursor = start + len(function) + 1
    depth = 1
    while cursor < len(text) and depth:
        if text[cursor] == "(":
            depth += 1
        elif text[cursor] == ")":
            depth -= 1
        cursor += 1
    return text[start + len(function) + 1 : cursor - 1] if not depth else None


def _split_arguments(arguments: str) -> list[str]:
    """Split a C# argument list on top-level commas only."""
    parts: list[str] = []
    depth = 0
    current: list[str] = []
    for char in arguments:
        if char in "(<":
            depth += 1
        elif char in ")>":
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if (tail := "".join(current).strip()) or parts:
        parts.append(tail)
    return parts


def _craft_minutes(body: str) -> float:
    """Read the base craft time out of a `CreateCraftTimeValue` call.

    The generator emits three shapes across the tree, and all three are live in
    0.13: named (`beneficiary: …, start: 6, …`), bare (`CreateCraftTimeValue(0.16f)`
    on simple block recipes), and the older positional form where the value is the
    third argument after a type and a UILink. Reading the argument list instead of
    pattern-matching the whole call keeps one code path across all three.
    """
    arguments = _call_arguments(body, "CreateCraftTimeValue")
    if arguments is None:
        return 0.0
    if named := _CRAFT_MINUTES_NAMED_RE.search(arguments):
        return _number(named.group("value"))
    parts = _split_arguments(arguments)
    if parts and _NUMBER_RE.fullmatch(parts[0]):
        return _number(parts[0].rstrip("f"))
    if len(parts) >= 3 and _NUMBER_RE.fullmatch(parts[2]):
        return _number(parts[2].rstrip("f"))
    return 0.0


@dataclass
class _ClassBlock:
    """One C# class plus the attribute run that precedes it."""

    name: str
    base: str
    attributes: str
    body: str


@dataclass
class _ParsedRecipe:
    """A parsed recipe plus whether it is a tag-product variant of a family.

    The distinction does not belong on the shipped DTO — a consumer wants the
    resolved recipe — but it is needed while folding, because a variant's labor,
    craft time, and skill live on its family's class rather than its own.
    """

    recipe: Recipe
    is_variant: bool


def _split_classes(text: str) -> list[_ClassBlock]:
    """Cut a source file into class blocks, keeping each class's attributes.

    Generated files usually hold one class, but tag-product families and a few
    item files declare several, so splitting on the class keyword rather than
    treating the file as one unit avoids attributing one class's station or skill
    to its neighbour.
    """
    matches = list(_CLASS_RE.finditer(text))
    blocks: list[_ClassBlock] = []
    for index, match in enumerate(matches):
        attr_start = matches[index - 1].end() if index else 0
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        blocks.append(
            _ClassBlock(
                name=match.group("name"),
                base=match.group("base"),
                attributes=text[attr_start : match.start()],
                body=text[match.end() : body_end],
            )
        )
    return blocks


def _parse_recipe(block: _ClassBlock, warnings: list[str]) -> _ParsedRecipe | None:
    """Build one `Recipe` from a `RecipeFamily` or tag-product `Recipe` class."""
    body = block.body
    name_match = _INIT_NAME_RE.search(body)
    if name_match is None:
        # A RecipeFamily with no Init is a template artifact, not a real recipe.
        return None
    name = name_match.group("value")

    display_match = _INIT_DISPLAY_RE.search(body) or _INITIALIZE_DISPLAY_RE.search(body)
    display_name = display_match.group(1) if display_match else prettify_eco_name(name)

    products: list[RecipeComponent] = [
        RecipeComponent(item=m.group("item"), quantity=_number(m.group("qty"), 1.0))
        for m in _PRODUCT_RE.finditer(body)
    ]
    if not products:
        warnings.append(f"{block.name}: no CraftingElement products parsed")
        return None

    ingredients = [
        RecipeComponent(
            item=m.group("type") or m.group("tag"),
            quantity=_number(m.group("qty")),
            is_tag=m.group("tag") is not None,
        )
        for m in _INGREDIENT_RE.finditer(body)
    ]
    # Eco models waste as GarbageOutput. It is a real output of the craft, so it
    # rides along as a byproduct rather than being dropped — a cost engine that
    # ignores slag understates what a craft actually puts into the world.
    garbage = [
        RecipeComponent(item=m.group("item"), quantity=_number(m.group("qty")))
        for m in _GARBAGE_RE.finditer(body)
    ]

    skill_match = _REQUIRES_SKILL_RE.search(block.attributes)

    station = ""
    family = ""
    if station_match := _ADD_RECIPE_RE.search(body):
        station = station_match.group("station")
    elif tag_match := _ADD_TAG_PRODUCT_RE.search(body):
        station = tag_match.group("station")
        family = tag_match.group("family")
    else:
        warnings.append(f"{block.name}: no crafting station registration found")

    return _ParsedRecipe(
        recipe=Recipe(
            name=name,
            display_name=display_name,
            product=products[0],
            ingredients=ingredients,
            byproducts=products[1:] + garbage,
            station=station,
            skill_name=skill_match.group("skill") if skill_match else None,
            skill_level=int(skill_match.group("level")) if skill_match else 0,
            labor_cost=_number(m.group("value")) if (m := _LABOR_RE.search(body)) else 0.0,
            craft_minutes=_craft_minutes(body),
            family=family or block.name,
        ),
        is_variant=block.base == "Recipe",
    )


def _parse_skill(block: _ClassBlock) -> dict[str, Any]:
    """Build a skill definition from a `: Skill` class in `Tech/`."""
    display = _LOC_DISPLAY_RE.search(block.attributes)
    tier = _TIER_RE.search(block.attributes)
    max_level = _MAX_LEVEL_RE.search(block.body)
    parent = _REQUIRES_SKILL_RE.search(block.attributes)
    return {
        "name": block.name,
        "displayName": display.group("value") if display else prettify_eco_name(block.name),
        "maxLevel": int(max_level.group("value")) if max_level else 0,
        "tier": int(tier.group("value")) if tier else None,
        # A specialty's RequiresSkill points at its profession (BakingSkill ->
        # ChefSkill), which is the profession axis eco-app#98 D needs.
        "profession": parent.group("skill") if parent else None,
        "tags": sorted({m.group("value") for m in _TAG_RE.finditer(block.attributes)}),
    }


def build_index_from_autogen(root: Path, *, source: str) -> RecipeIndex:
    """Walk an `AutoGen` tree and fold every recipe, skill, and tag into an index.

    `root` is the `Mods/__core__/AutoGen` directory of a dedicated-server install.
    Recipes are not confined to `Recipe/` — 396 of them live in `WorldObject/` and
    the rest are spread across `Item/`, `Food/`, `Clothing/`, and six more — so the
    walk covers the whole tree rather than one directory.
    """
    if not root.is_dir():
        raise FileNotFoundError(f"AutoGen root not found: {root}")

    warnings: list[str] = []
    parsed: list[_ParsedRecipe] = []
    skills: list[dict[str, Any]] = []
    tags: dict[str, list[str]] = {}

    for path in sorted(root.rglob("*.cs")):
        if any(part in _SKIP_DIRS for part in path.relative_to(root).parts[:-1]):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for block in _split_classes(text):
            if block.base == "Skill":
                skills.append(_parse_skill(block))
            elif block.base in {"RecipeFamily", "Recipe"}:
                if (entry := _parse_recipe(block, warnings)) is not None:
                    parsed.append(entry)
            # Tags are declared on the class that carries them — items, blocks,
            # world objects — so collect from every class, not just recipes.
            for tag_match in _TAG_RE.finditer(block.attributes):
                tags.setdefault(tag_match.group("value"), []).append(block.name)

    _resolve_variants(parsed, warnings)
    index = RecipeIndex(
        fetched_at_iso=datetime.now(UTC).isoformat(),
        source=source,
        recipes=sorted((entry.recipe for entry in parsed), key=lambda r: r.name),
        skills=sorted(skills, key=lambda s: str(s["name"])),
        tags={k: sorted(set(v)) for k, v in sorted(tags.items())},
        warnings=warnings,
    )
    _build_lookups(index)
    return index


def _resolve_variants(parsed: list[_ParsedRecipe], warnings: list[str]) -> None:
    """Push each family's labor, craft time, and skill onto its tag-product variants.

    A `: Recipe` variant declares only its own ingredient list; Eco applies the
    owning family's cost when it is crafted. Left unresolved, 365 of 1,487 recipes
    would report `laborCost: 0` and `craftMinutes: 0` — a plausible-looking answer
    that says a bench is free to make, which is exactly the class of defect the
    eco-app#240 sweep flagged.
    """
    heads = {entry.recipe.family: entry.recipe for entry in parsed if not entry.is_variant}
    for entry in parsed:
        if not entry.is_variant:
            continue
        head = heads.get(entry.recipe.family)
        if head is None:
            warnings.append(
                f"{entry.recipe.name}: tag-product variant of {entry.recipe.family}, "
                "whose family class was not parsed; labor and craft time unresolved"
            )
            continue
        entry.recipe.labor_cost = entry.recipe.labor_cost or head.labor_cost
        entry.recipe.craft_minutes = entry.recipe.craft_minutes or head.craft_minutes
        entry.recipe.skill_name = entry.recipe.skill_name or head.skill_name
        entry.recipe.skill_level = entry.recipe.skill_level or head.skill_level


def _build_lookups(index: RecipeIndex) -> None:
    """Fill the by-product / by-skill / by-station maps and variant lists."""
    by_family: dict[str, list[str]] = {}
    for recipe in index.recipes:
        index.by_product.setdefault(recipe.product.item, []).append(recipe.name)
        index.by_station.setdefault(recipe.station, []).append(recipe.name)
        if recipe.skill_name:
            index.by_skill.setdefault(recipe.skill_name, []).append(recipe.name)
        by_family.setdefault(recipe.family, []).append(recipe.name)

    for recipe in index.recipes:
        siblings = by_family.get(recipe.family, [])
        recipe.variants = [name for name in siblings if name != recipe.name]
        # The family's own recipe is the one Eco crafts unless a player picks a
        # tag variant, so it is the default; a family of one is trivially default.
        recipe.is_default = recipe.family.removesuffix("Recipe") == recipe.name or not siblings


__all__ = [
    "AUTOGEN_SOURCE_TEMPLATE",
    "build_index_from_autogen",
]
