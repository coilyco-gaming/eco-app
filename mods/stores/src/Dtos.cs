using System.Text.Json.Serialization;
using Newtonsoft.Json;

namespace EcoStoreExporter;

// Dual JSON attributes so DTOs serialize camelCase under System.Text.Json
// (shell harness) or Newtonsoft.Json (Eco's web pipeline). Same pattern as
// mods/jobs. The shape is the contract the Python store-directory and
// logistics siblings upgrade to - see ../docs/dto.md.

// A single tradeable line on a store shelf. `Buying` is from the STORE's point
// of view: true = the store buys this item (players sell to it), false = the
// store sells it (players buy from it) - matching DiscordLink's buy/sell split.
// `Quantity` is current stock for a sell offer, or the amount still wanted for a
// buy offer. `Price` is in the store's `Currency` (see the parent StoreDto).
public record OfferDto(
    [property: JsonPropertyName("item"), JsonProperty("item")] string Item,
    [property: JsonPropertyName("itemTypeName"), JsonProperty("itemTypeName")] string? ItemTypeName,
    [property: JsonPropertyName("buying"), JsonProperty("buying")] bool Buying,
    [property: JsonPropertyName("price"), JsonProperty("price")] double Price,
    [property: JsonPropertyName("quantity"), JsonProperty("quantity")] int Quantity);

// World coordinates of the store object, rounded to whole blocks. Null when the
// object's position could not be read (an orphaned store surviving a save
// migration - see the dangling-reference note in ../docs/dto.md).
public record LocationDto(
    [property: JsonPropertyName("x"), JsonProperty("x")] int X,
    [property: JsonPropertyName("y"), JsonProperty("y")] int Y,
    [property: JsonPropertyName("z"), JsonProperty("z")] int Z);

// One live store shelf: its name, owner, currency, location, and every current
// offer. `Owner` and `Currency` are nullable because an unowned or
// currency-less store is legal in Eco. This is the shelf-accurate snapshot the
// siblings need to move from history-derived to live `Trades <item>` parity.
public record StoreDto(
    [property: JsonPropertyName("name"), JsonProperty("name")] string Name,
    [property: JsonPropertyName("owner"), JsonProperty("owner")] string? Owner,
    [property: JsonPropertyName("currency"), JsonProperty("currency")] string? Currency,
    [property: JsonPropertyName("location"), JsonProperty("location")] LocationDto? Location,
    [property: JsonPropertyName("offers"), JsonProperty("offers")] OfferDto[] Offers);

// One account's balance in a single currency, the row DiscordLink's
// `Currency <name>` top-holders table shows. `Account` is the bank account's
// display name (already human-readable in Eco); `Holder` is the resolved owner
// citizen name (via the same UserManager join mods/jobs uses for
// /api/v1/citizens), or null when the account has no single resolvable owner (a
// government/company account, or a user the join missed). See ../docs/currency-holdings.md.
public record HolderDto(
    [property: JsonPropertyName("account"), JsonProperty("account")] string Account,
    [property: JsonPropertyName("holder"), JsonProperty("holder")] string? Holder,
    [property: JsonPropertyName("balance"), JsonProperty("balance")] double Balance);

// Per-currency holdings: the top account balances plus the totals they sum
// toward. `Backed` is best-effort (null when the currency's money-type could
// not be read) - the Python side keeps its own minted/personal classification
// from the MintCurrency action; this is supplementary. `AccountsCounted` and
// `TotalHoldings` are over ALL accounts holding the currency, not just the
// truncated `TopHolders` list, so the report can say "top 20 of N". This is the
// surface eco-app#58 adds: the one piece of `Currency <name>` history cannot
// reconstruct, read live from CurrencyManager in-process.
public record CurrencyHoldingsDto(
    [property: JsonPropertyName("currency"), JsonProperty("currency")] string Currency,
    // The Currency object's in-game id, as a string. The action exporter keys
    // CurrencyTrade rows by this id rather than by name, so without it eco-app
    // cannot join a trade to the currency it was denominated in: every trade
    // landed on an id-named phantom currency and all 167 real ones read zero
    // (eco-app#217). Null when the id member could not be read.
    [property: JsonPropertyName("id"), JsonProperty("id")] string? Id,
    [property: JsonPropertyName("backed"), JsonProperty("backed")] bool? Backed,
    [property: JsonPropertyName("accountsCounted"), JsonProperty("accountsCounted")] int AccountsCounted,
    [property: JsonPropertyName("totalHoldings"), JsonProperty("totalHoldings")] double TotalHoldings,
    [property: JsonPropertyName("topHolders"), JsonProperty("topHolders")] HolderDto[] TopHolders);
