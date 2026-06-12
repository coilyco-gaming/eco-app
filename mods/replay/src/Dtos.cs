using System.Text.Json.Serialization;
using Newtonsoft.Json;

namespace EcoReplay;

// Both attribute sets present so the DTO serializes as camelCase under
// either System.Text.Json or Newtonsoft.Json (Eco's bundled pipeline).
public record EventDto(
    [property: JsonPropertyName("id"), JsonProperty("id")] long Id,
    [property: JsonPropertyName("unixTime"), JsonProperty("unixTime")] long UnixTime,
    [property: JsonPropertyName("gameTime"), JsonProperty("gameTime")] int GameTime,
    [property: JsonPropertyName("type"), JsonProperty("type")] string Type,
    [property: JsonPropertyName("citizen"), JsonProperty("citizen")] string? Citizen,
    [property: JsonPropertyName("body"), JsonProperty("body")] string BodyJson);
