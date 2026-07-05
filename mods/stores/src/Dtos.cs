using System.Text.Json.Serialization;
using Newtonsoft.Json;

namespace EcoStoreExporter;

// Dual JSON attributes so DTOs serialize camelCase under System.Text.Json
// (shell harness) or Newtonsoft.Json (Eco's web pipeline). Same pattern as
// mods/jobs. The shape is the contract the Python store-directory and
// logistics siblings upgrade to - see docs/dto.md.

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
// migration - see the dangling-reference note in docs/dto.md).
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
