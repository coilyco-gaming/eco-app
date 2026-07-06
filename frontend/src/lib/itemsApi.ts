// Typed clients for the item directory + per-item pivot (eco-app#81).
//
// `/preview/items.json` returns ItemIndex.to_dict() from eco_mcp_app/items.py:
// the union of every item ever bought / sold / crafted, each row carrying its
// trade count / currency volume / crafted quantity.
//
// `/preview/item.json?item=<id>` returns ItemPivot.to_dict(): every individual
// trade and crafting event that pivots on one item id, newest first. Party /
// crafter ids are already joined to names (falling back to "Citizen #<id>").

export interface ItemStat {
  item: string
  tradeCount: number
  tradeVolume: number
  craftCount: number
}

export interface ItemIndex {
  fetchedAtISO: string
  sourceBaseUrl: string
  totalItems: number
  items: ItemStat[]
  warnings: string[]
}

// One trade row for an item — mirrors a trades-ledger row (tradesApi.Trade).
export interface ItemTrade {
  tradeType: string
  time: number
  day: number
  buyer: string
  seller: string
  shopOwner: string
  item: string
  quantity: number
  currency: string
  currencyAmount: number
  unitPrice: number | null
  store: string
  location: string
  direction: string
}

// One crafting/production event for an item.
export interface ItemCraft {
  actionType: string
  time: number
  day: number
  citizen: string
  station: string
  quantity: number
}

export interface ItemPivot {
  fetchedAtISO: string
  sourceBaseUrl: string
  item: string
  trades: ItemTrade[]
  crafts: ItemCraft[]
  tradeCount: number
  tradeVolume: number
  craftCount: number
  craftQuantity: number
  warnings: string[]
}

export async function fetchItemIndex(signal?: AbortSignal): Promise<ItemIndex> {
  const resp = await fetch("/preview/items.json", { signal })
  if (!resp.ok) {
    throw new Error(`item index fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as ItemIndex
}

export async function fetchItemPivot(item: string, signal?: AbortSignal): Promise<ItemPivot> {
  const resp = await fetch(`/preview/item.json?item=${encodeURIComponent(item)}`, { signal })
  if (!resp.ok) {
    throw new Error(`item pivot fetch failed: HTTP ${resp.status}`)
  }
  return (await resp.json()) as ItemPivot
}
