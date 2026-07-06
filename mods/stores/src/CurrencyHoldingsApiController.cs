using Microsoft.AspNetCore.Mvc;

namespace EcoStoreExporter;

// Lives inside the Eco server process. Eco's ASP.NET Core host picks up
// [ApiController] classes from mod assemblies via AddApplicationPart, so this
// route joins the server's existing /api/v1/* surface, guarded by the same
// admin-token middleware (the `X-API-Key` header) as the other routes - the mod
// adds no auth of its own (same as mods/jobs and the stores route).
//
// Returns, per currency, the top account balances live from CurrencyManager:
// the DiscordLink `Currency <name>` top-holders piece that trade history cannot
// reconstruct (eco-app#58). Consumed by eco_mcp_app/currency.py's per-currency
// report. See docs/currency-holdings.md.
[ApiController]
[Route("api/v1/currency-holdings")]
public class CurrencyHoldingsApiController : ControllerBase
{
    [HttpGet]
    public IEnumerable<CurrencyHoldingsDto> Get() => CurrencyHoldingsScanner.Scan();
}
