import { cleanup, render, screen, waitFor } from "@testing-library/react"
import { afterEach, describe, expect, it, vi } from "vitest"
import { MemoryRouter } from "react-router-dom"
import Recipe from "./Recipe"

// Two recipes producing the SAME product (SteelBar) two ways, so the "other
// ways to make it" cross-link (built from byProduct, not just same-family
// variants) has a sibling to point at.
const INDEX = {
  fetchedAtISO: "2026-07-07T13:00:00+00:00",
  source: "test",
  version: 1,
  counts: { recipes: 2, skills: 1, tags: 1, products: 1, stations: 2 },
  recipes: [
    {
      name: "SteelBarRecipe",
      displayName: "Steel Bar",
      product: { item: "SteelBarItem", displayName: "Steel Bar", quantity: 2, isTag: false },
      ingredients: [
        { item: "IronBarItem", displayName: "Iron Bar", quantity: 4, isTag: false },
        { item: "Charcoal", displayName: "Charcoal", quantity: 3, isTag: true },
      ],
      byproducts: [{ item: "SlagItem", displayName: "Slag", quantity: 1, isTag: false }],
      station: "BloomeryItem",
      stationDisplayName: "Bloomery",
      skill: { name: "SmeltingSkill", level: 2 },
      laborCost: 100,
      craftMinutes: 0.5,
      tableTierRequired: null,
      variants: [],
      family: "Steel Bar",
      isDefault: true,
      isBlueprint: false,
    },
    {
      name: "SteelBarBlastRecipe",
      displayName: "Steel Bar (Blast Furnace)",
      product: { item: "SteelBarItem", displayName: "Steel Bar", quantity: 5, isTag: false },
      ingredients: [{ item: "IronBarItem", displayName: "Iron Bar", quantity: 8, isTag: false }],
      byproducts: [],
      station: "BlastFurnaceItem",
      stationDisplayName: "Blast Furnace",
      skill: { name: "AdvancedSmeltingSkill", level: 4 },
      laborCost: 200,
      craftMinutes: 1,
      tableTierRequired: null,
      variants: [],
      family: "Steel Bar",
      isDefault: false,
      isBlueprint: false,
    },
  ],
  byProduct: { SteelBarItem: ["SteelBarRecipe", "SteelBarBlastRecipe"] },
  bySkill: {
    SmeltingSkill: ["SteelBarRecipe"],
    AdvancedSmeltingSkill: ["SteelBarBlastRecipe"],
  },
  byStation: { BloomeryItem: ["SteelBarRecipe"], BlastFurnaceItem: ["SteelBarBlastRecipe"] },
  skills: [{ name: "SmeltingSkill", displayName: "Smelting", maxLevel: 7 }],
  tags: { Charcoal: ["CharcoalItem"] },
  warnings: [],
}

function stubFetch(payload: unknown, ok = true) {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(JSON.stringify(payload), {
        status: ok ? 200 : 500,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  )
}

function renderRecipe(entry: string) {
  return render(
    <MemoryRouter initialEntries={[entry]}>
      <Recipe />
    </MemoryRouter>,
  )
}

afterEach(() => {
  cleanup()
  vi.restoreAllMocks()
})

describe("Recipe", () => {
  it("renders the BOM, facts, and product market cross-link", async () => {
    stubFetch(INDEX)
    renderRecipe("/recipe?id=SteelBarRecipe")

    await waitFor(() => {
      expect(screen.getByTestId("recipe-pill")).toHaveTextContent("makes 2× Steel Bar")
    })
    // Ingredients (item + tag) and byproduct render.
    expect(screen.getByTestId("recipe-ingredients")).toHaveTextContent("Iron Bar")
    expect(screen.getByTestId("recipe-ingredients")).toHaveTextContent("Charcoal")
    expect(screen.getByTestId("recipe-products")).toHaveTextContent("Slag")
    // Facts: profession + labor.
    expect(screen.getByTestId("recipe-facts")).toHaveTextContent("Smelting")
    expect(screen.getByTestId("recipe-facts")).toHaveTextContent("100 cal")
    // The market cross-link points at the product's item page.
    expect(screen.getByTestId("recipe-market-link")).toHaveAttribute(
      "href",
      "/item?item=SteelBarItem",
    )
    expect(screen.getByTestId("recipe-resolver-link")).toHaveAttribute(
      "href",
      "/uses/resolve?item=SteelBarItem",
    )
  })

  it("lists other recipes that make the same product", async () => {
    stubFetch(INDEX)
    renderRecipe("/recipe?id=SteelBarRecipe")

    await waitFor(() => {
      expect(screen.getByTestId("recipe-alternates")).toBeInTheDocument()
    })
    // The blast-furnace sibling shows and deep-links to its own detail.
    expect(screen.getByText("Steel Bar (Blast Furnace)").closest("a")).toHaveAttribute(
      "href",
      "/recipe?id=SteelBarBlastRecipe",
    )
  })

  it("tag ingredients offer a reverse-lookup but no item link", async () => {
    stubFetch(INDEX)
    renderRecipe("/recipe?id=SteelBarRecipe")

    await waitFor(() => {
      expect(screen.getByTestId("recipe-ingredients")).toBeInTheDocument()
    })
    // The item ingredient links to /item; the tag ingredient does not.
    expect(screen.getByText("Iron Bar").closest("a")).toHaveAttribute(
      "href",
      "/item?item=IronBarItem",
    )
    expect(screen.getByText("Charcoal").closest("a")).toBeNull()
  })

  it("shows the missing-selection note with no id", async () => {
    stubFetch(INDEX)
    renderRecipe("/recipe")

    await waitFor(() => {
      expect(screen.getByTestId("recipe-missing")).toBeInTheDocument()
    })
  })

  it("shows a not-found note for an unknown id (degraded deep link)", async () => {
    stubFetch(INDEX)
    renderRecipe("/recipe?id=NoSuchRecipe")

    await waitFor(() => {
      expect(screen.getByTestId("recipe-not-found")).toBeInTheDocument()
    })
  })

  it("surfaces a fetch error without crashing", async () => {
    stubFetch({}, false)
    renderRecipe("/recipe?id=SteelBarRecipe")

    await waitFor(() => {
      expect(screen.getByTestId("recipe-error")).toBeInTheDocument()
    })
  })
})
