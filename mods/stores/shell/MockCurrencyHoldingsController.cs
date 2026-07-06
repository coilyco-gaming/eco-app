using EcoStoreExporter;
using Microsoft.AspNetCore.Mvc;

namespace EcoStoreExporter.Shell;

// Same route and DTOs as the real mod with canned data, so the Python currency
// consumer can develop and test the per-currency holder report against a live
// C# HTTP server without booting Eco (the pattern mods/jobs and the stores
// route use). The shelves below cover the shapes the real scanner emits: a
// minted/backed currency held across several accounts (one government account
// with no single owner -> null holder), and a personal/credit currency held by
// its own player. See docs/currency-holdings.md.
[ApiController]
[Route("api/v1/currency-holdings")]
public class MockCurrencyHoldingsController : ControllerBase
{
    [HttpGet]
    public IEnumerable<CurrencyHoldingsDto> Get()
    {
        return new[]
        {
            new CurrencyHoldingsDto(
                Currency: "Sirens Credit",
                Backed: true,
                AccountsCounted: 4,
                TotalHoldings: 18250.0,
                TopHolders: new[]
                {
                    new HolderDto("Treasury", null, 9000.0),
                    new HolderDto("redwood's Personal Account", "redwood", 5200.0),
                    new HolderDto("salt's Personal Account", "salt", 3050.0),
                    new HolderDto("Roadside Stall Account", "corn_grower", 1000.0),
                }),
            new CurrencyHoldingsDto(
                Currency: "redwood Credit",
                Backed: false,
                AccountsCounted: 2,
                TotalHoldings: 640.0,
                TopHolders: new[]
                {
                    new HolderDto("redwood's Personal Account", "redwood", 600.0),
                    new HolderDto("salt's Personal Account", "salt", 40.0),
                }),
        };
    }
}
