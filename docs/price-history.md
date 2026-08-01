# Current-cycle item price history

The item-pricing use case at `/uses/price?item=<id>&currency=<name>` joins three
existing sources for one current Eco cycle:

* the normalized trade ledger supplies observed unit prices, day buckets, and volume
* the bundled recipe graph supplies every known recipe variant and its required specialty
* the progression action export supplies the first server-wide observation of each required specialty gain

The join is exposed at
`/preview/price-history.json?item=<id>&currency=<name>`. Item and currency are
both required. Prices from separate currencies are never blended.

## Distribution evidence

The response names its window as `Current cycle` and includes sample count,
freshness, median, range, p10/p25/p50/p75/p90, equal-width histogram buckets,
daily median/min/max/volume rows, and the newest observed cycle day. The SPA
draws the histogram directly. It never fits or implies a normal curve.

Quality stays explicit:

* `no_data` means no priced observations match the selected item and currency
* `thin` means fewer than five observations
* `stale` means the selected item's latest trade trails newer cycle evidence by at least three days
* `multimodal` means two material occupied histogram groups are separated by an empty range

An isolated outlier stays visible in the histogram and percentile evidence but
does not become a second mode unless it carries a material share of samples.

## Specialty markers

Every recipe returned by the recipe graph's product lookup is included. Variant
links are followed before required specialties are deduplicated. Progression
folding records each specialty's first gain from the uncapped event set, before
per-citizen presentation limits apply. The SPA overlays observed unlock days on
the daily price timeline and lists the recipe variants behind every marker.

The degraded states do not overclaim:

* `missing_recipes` means the graph has no producing recipe for the item
* `missing_progression` means the `GainSpecialty` export was unavailable
* `unobserved_unlocks` means the export was available but a required specialty had no observed gain

An unobserved gain does not prove that a specialty was never available.

## Cycle boundary

The contract sets `historicalCyclesIncluded` to `false` and labels its
progression semantics `current-cycle-v1`. Older cycles can have different star
or progression rules, so the service does not average them together. A future
cross-cycle view must version each ruleset explicitly before comparison.

## Verification

Backend tests cover a complete multi-variant join, representative, thin, empty,
stale, multimodal, and outlier-heavy histories plus every recipe/progression
degraded state. Frontend tests cover currency selection, distribution evidence,
marker overlays, current-cycle labeling, and degraded presentations.

## See also

* [docs/uses.md](uses.md) - the item-pricing workflow
* [docs/recipes.md](recipes.md) - recipe graph provenance and DTO
* [docs/progression.md](progression.md) - progression action ingest
* [docs/trades.md](trades.md) - normalized trade ledger
