using EcoStoreExporter;
using Microsoft.AspNetCore.Mvc;

namespace EcoStoreExporter.Shell;

// Same route and DTOs as the real mod with canned data, so the Python
// store-directory and logistics siblings can develop and test against a live
// C# HTTP server without booting Eco (the pattern mods/jobs uses). The shelves
// below cover the shapes the real scanner emits: sell offers, buy offers, a
// store with no owner, and a store with no currency set. See docs/dto.md.
[ApiController]
[Route("api/v1/stores")]
public class MockStoresController : ControllerBase
{
    [HttpGet]
    public IEnumerable<StoreDto> Get()
    {
        return new[]
        {
            new StoreDto(
                Name: "Redwood Lumber Depot",
                Owner: "redwood",
                Currency: "Sirens Credit",
                Location: new LocationDto(412, 68, 1180),
                Offers: new[]
                {
                    new OfferDto("Lumber", "LumberItem", Buying: false, Price: 1.25, Quantity: 480),
                    new OfferDto("Board", "BoardItem", Buying: false, Price: 0.60, Quantity: 1200),
                    new OfferDto("Log", "LogItem", Buying: true, Price: 0.35, Quantity: 640),
                }),
            new StoreDto(
                Name: "Salt's Smeltery Outlet",
                Owner: "salt",
                Currency: "Sirens Credit",
                Location: new LocationDto(905, 74, 512),
                Offers: new[]
                {
                    new OfferDto("Iron Ingot", "IronIngotItem", Buying: false, Price: 3.10, Quantity: 220),
                    new OfferDto("Iron Ore", "IronOreItem", Buying: true, Price: 0.90, Quantity: 300),
                }),
            new StoreDto(
                Name: "Roadside Barter Stall",
                Owner: null,
                Currency: null,
                Location: new LocationDto(120, 66, 88),
                Offers: new[]
                {
                    new OfferDto("Corn", "CornItem", Buying: false, Price: 0.0, Quantity: 64),
                }),
        };
    }
}
