# Price history

Per-item price movement over a cycle, and how it is evidenced.

## Distribution evidence

A price series is only meaningful with the spread behind it, so each point
carries the distribution rather than a bare mean. A single trade and fifty
trades at the same mean are different facts, and the surface says which.

## Specialty markers

Progression events are overlaid on the series, so a price move that follows a
citizen gaining the relevant specialty is visible as such rather than being
left for the reader to correlate by eye.

## Cycle boundary

Prices do not carry across a cycle boundary. A new cycle is a new world with a
new economy, so the series restarts rather than continuing a line that would
imply continuity that does not exist.

## Verification

The series is checked against the trades ledger for the same item and window.
They are derived from the same detailed rows, so a divergence is a parser bug
rather than a modelling choice.

## See also

- [trades.md](trades.md) - the ledger this derives from.
- [cost.md](cost.md) - the cost model prices are compared against.
