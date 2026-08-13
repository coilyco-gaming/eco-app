"""Trades are attributed to named currencies, not to raw ids (eco-app#217).

Eco's action exporter keys a CurrencyTrade row by the Currency object's *id*,
while CreateCurrency writes its *name*, so the two never joined. On Sirens that
split perfectly the wrong way: 18 currencies whose "name" was a bare number
carried all 3,668 trades, and the 167 real ones carried zero between them.
`get_currency(currency="Spectres")` resolved and then reported tradeCount 0
while `find_trade` could see Spectres in active use.

The ledger side had the mirror defect: `_clean_name` treats a bare number as a
misalignment artifact, so it blanked the id and every one of the 526 detailed
rows reported `currency: ""` — in a payload that simultaneously set
`trade_currency_column_seen: true`.

The join key comes from the stores/economy exporter mod's holdings surface,
which is the only place a Currency id and its name appear together
(`CurrencyHoldingsDto.Id`).
"""

from __future__ import annotations

from eco_mcp_app.currency import (
    CurrencyRecord,
    CurrencySnapshot,
    _resolve_currency_ids,
    compute_currency_payload,
)
from eco_mcp_app.trades import _currency_cell, _ParsedTrade, resolve_parsed_currencies


def _trade(currency: str) -> _ParsedTrade:
    return _ParsedTrade(
        trade_type="CurrencyTrade",
        time_s=1.0,
        day=0.0,
        buyer_id="1",
        seller_id="2",
        shop_owner_id="2",
        item="CementItem",
        quantity=3.0,
        currency=currency,
        currency_amount=1.8,
        unit_price=0.6,
        store="StoreItem",
        location="1,2,3",
        direction="buy",
        event_count=1,
        is_rollup=False,
    )


def test_the_ledger_keeps_a_numeric_currency_id() -> None:
    # `_clean_name` blanked this, which is why every detailed row came back
    # with an empty currency.
    assert _currency_cell("2533707") == "2533707"
    assert _currency_cell("Spectres") == "Spectres"
    # A position triple is still a misalignment artifact.
    assert _currency_cell("419,75,458") == ""
    assert _currency_cell("  ") == ""


def test_parsed_rows_resolve_ids_to_names() -> None:
    parsed = [_trade("2533707"), _trade("2533707"), _trade("Racines")]
    unresolved = resolve_parsed_currencies(parsed, {"2533707": "Spectres"})
    assert [t.currency for t in parsed] == ["Spectres", "Spectres", "Racines"]
    assert unresolved == 0


def test_an_unmapped_id_is_kept_and_counted_not_dropped() -> None:
    # The volume is real even when the mod cannot name the currency, so the row
    # survives — and the count comes back so the caller can be told.
    parsed = [_trade("999999"), _trade("2533707")]
    unresolved = resolve_parsed_currencies(parsed, {"2533707": "Spectres"})
    assert [t.currency for t in parsed] == ["999999", "Spectres"]
    assert unresolved == 1


def _snapshot(records: list[CurrencyRecord], id_map: dict[str, str]) -> CurrencySnapshot:
    snap = CurrencySnapshot(
        fetched_at_iso="t",
        source_base_url="http://eco.example.com:3001",
        info={},
        days_elapsed=40,
        admin_ok=True,
    )
    for rec in records:
        snap.currencies[rec.name] = rec
    snap.currency_id_to_name = id_map
    return snap


def test_id_keyed_trade_totals_fold_onto_the_named_currency() -> None:
    """The headline defect: named currencies reporting zero trades."""
    named = CurrencyRecord("Spectres", is_minted=True, trade_count=0, trade_volume=0.0)
    phantom = CurrencyRecord("2533707", trade_count=3668, trade_volume=12345.0)
    snap = _snapshot([named, phantom], {"2533707": "Spectres"})

    _resolve_currency_ids(snap)

    assert "2533707" not in snap.currencies
    spectres = snap.currencies["Spectres"]
    assert spectres.trade_count == 3668
    assert spectres.trade_volume == 12345.0
    # The merge keeps the named record's own facts.
    assert spectres.is_minted is True
    assert snap.warnings == []


def test_an_unmapped_id_is_flagged_rather_than_named() -> None:
    phantom = CurrencyRecord("2967954", trade_count=412, trade_volume=99.0)
    snap = _snapshot([phantom], {})

    _resolve_currency_ids(snap)

    # Kept — the trades happened — but never presented as a currency name.
    rec = snap.currencies["2967954"]
    assert rec.unresolved_id is True
    assert rec.trade_count == 412
    assert len(snap.warnings) == 1
    assert "412 trade(s) are attributed to currency ids" in snap.warnings[0]

    view = compute_currency_payload(snap)["currencies"][0]
    assert view["unresolvedId"] is True
    assert view["currencyId"] == "2967954"


def test_a_resolved_currency_reports_no_unresolved_id() -> None:
    named = CurrencyRecord("Spectres", trade_count=10, trade_volume=5.0, currency_id="2533707")
    snap = _snapshot([named], {"2533707": "Spectres"})
    _resolve_currency_ids(snap)
    view = compute_currency_payload(snap)["currencies"][0]
    assert view["unresolvedId"] is False
    assert view["currencyId"] == "2533707"
    assert view["name"] == "Spectres"
