# `/api/v1/currency-holdings` DTO contract

The shape the live currency-holdings exporter emits, and the contract
`eco_mcp_app/currency.py`'s per-currency report consumes. Built in
[eco-app#58](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/58)
under the DiscordLink-replacement epic
([#37](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/37)).

## Why this exists

`get_currency` already meets DiscordLink's `Currencies` and most of
`Currency <name>` from the admin dataset + action-exporter surface. The one
piece history cannot reconstruct is the **top-holders list**:

- `PersonalWealthInDefaultCurrency` / `GovernmentHoldingsInDefaultCurrency` are
  single **aggregate** series in the default currency, not per-account and not
  per-currency.
- `CurrencyTrade` rows give buyer/seller **flows**, not balances, and the
  numeric ids still hit the id-to-name join blocker ([#5](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/5)).

It is also the only place a Currency's **id** and its **name** appear
together, which is what makes trade attribution possible at all: the action
exporter keys `CurrencyTrade` rows by id, so without this map every trade lands
on an id-named phantom currency and every real one reports zero
([#217](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/217)).

Only the in-process `CurrencyManager` carries per-account, per-currency
balances. This endpoint reads them live and joins account owners to citizen
names via the same `UserManager` access `mods/jobs` uses for
`/api/v1/citizens`.

## Endpoint

```
GET /api/v1/currency-holdings
X-API-Key: <admin token>
```

Same admin-token surface as the other `/api/v1/*` admin routes (and the stores
route). Returns a JSON array, one entry per currency.

## Shape

```jsonc
[
  {
    "currency": "Sirens Credit",   // currency display name
    "id": "2533707",               // in-game Currency id, or null (unread)
    "backed": true,                // minted/backed vs personal/credit, or null (unread)
    "accountsCounted": 4,          // accounts holding this currency (ALL, not just topHolders)
    "totalHoldings": 18250.0,      // sum of every holding (ALL accounts)
    "topHolders": [
      {
        "account": "Treasury",     // bank account display name (already human-readable)
        "holder": null,            // resolved owner citizen name, or null (see below)
        "balance": 9000.0          // this account's balance in this currency
      }
    ]
  }
]
```

### Field semantics

- **`backed`** is best-effort (`Currency.Backed` / `CurrencyType`), **null**
  when the money-type could not be read. The Python side keeps its own
  minted/personal classification from the `MintCurrency` action; this is
  supplementary, not authoritative.
- **`accountsCounted`** and **`totalHoldings`** are over **all** accounts
  holding the currency, not just the truncated `topHolders`, so the report can
  honestly say "top N of `accountsCounted`". Truncation never distorts the
  money-supply figure.
- **`topHolders`** is capped by the mod (25) and re-capped by the Python
  consumer (15). Ranked by balance, descending.
- **`holder`** is the account's single owner citizen name, joined via
  `UserManager`. It is **null** for a government/company account with no single
  owner, or a user the join missed. The `account` name always carries the row.

## Nulls and dangling references

The scanner walks live economy state, which is not clean. The
gaming-eco-investigation case library records reproducible NREs in Eco's own
trade/economy paths from orphaned accounts and currencies removed by a mod
update surviving a save migration. So `CurrencyHoldingsScanner` reads every
economy member by name, guarded, and **skips-and-continues** rather than
throwing. A **partial holdings table is a valid response**; a 500 is not.
Reading by name also keeps the mod **compiling** across Eco reference-assembly
versions that rename members (the one typed touchpoint is `UserManager`, as in
`mods/jobs`). Full rationale is in the header of
[`src/CurrencyHoldingsScanner.cs`](../src/CurrencyHoldingsScanner.cs).

## Reachable vs unavailable, on the Python side

The exporter DLL lands on the server out of band, at the next natural restart
(same as the stores route - a new plugin needs a restart, which
[#55](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/55) is built
to avoid). Until it is deployed the endpoint 404s. `currency.py` treats that as
best-effort: an unreachable endpoint leaves each record's `holdersReachable`
false and the per-currency report renders `HOLDERS_UNAVAILABLE_NOTE` rather
than faking a list. Reachable-but-empty ("no accounts hold this currency yet")
is a distinct, valid state.

## Local development

The shell harness (`mods/stores/shell`) serves this exact shape with mock data
on `:5101`, so the Python consumer can be built and tested with no live Eco
server:

```sh
ward exec run-shell-stores   # -> http://localhost:5101/api/v1/currency-holdings
```
