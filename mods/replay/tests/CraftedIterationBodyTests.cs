using Newtonsoft.Json.Linq;
using Xunit;

namespace EcoReplay.Tests;

public class CraftedIterationBodyTests
{
    [Fact]
    public void Serialize_UsesTheFixedMinimalCraftSchema()
    {
        var json = JObject.Parse(CraftedIterationBody.Serialize(
            item: "StumpLatrineItem",
            station: "CarpentryTableItem",
            byproduct: "CompostItem",
            position: "(12, 4, -8)"));

        Assert.Equal(
            new[] { "schema", "item", "station", "byproduct", "position", "iterations" },
            json.Properties().Select(property => property.Name));
        Assert.Equal(CraftedIterationBody.Schema, (string?)json["schema"]);
        Assert.Equal("StumpLatrineItem", (string?)json["item"]);
        Assert.Equal("CarpentryTableItem", (string?)json["station"]);
        Assert.Equal("CompostItem", (string?)json["byproduct"]);
        Assert.Equal("(12, 4, -8)", (string?)json["position"]);
        Assert.Equal(1, (int?)json["iterations"]);
    }
}
