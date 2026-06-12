using Microsoft.AspNetCore.Mvc;

namespace EcoReplay;

// HTTP surface for the recorded events.
//
// Same shape as eco-jobs-tracker: a small JSON API mounted under /api/v1/
// that the Python web app drives. Eco's ASP.NET host auto-registers
// [ApiController] types from loaded mod assemblies, so no plugin glue.
[ApiController]
[Route("api/v1/events")]
public class EventsApiController : ControllerBase
{
    [HttpGet]
    public IActionResult Get(
        [FromQuery] string? citizen = null,
        [FromQuery] string? type = null,
        [FromQuery] int limit = 100,
        [FromQuery] long? since = null)
    {
        var plugin = EcoReplayPlugin.Instance;
        if (plugin == null || !plugin.Store.IsReady)
        {
            return StatusCode(503, new { error = "EcoReplay store not ready" });
        }

        var rows = plugin.Store
            .Query(citizen, type, limit, since)
            .Select(r => new EventDto(
                r.Id, r.UnixTimeSeconds, r.GameTimeSeconds,
                r.ActionType, r.Citizen, r.BodyJson))
            .ToList();

        return new JsonResult(new { events = rows, count = rows.Count });
    }

    [HttpGet("stats")]
    public IActionResult Stats()
    {
        var plugin = EcoReplayPlugin.Instance;
        if (plugin == null) return StatusCode(503);
        return new JsonResult(new
        {
            ready = plugin.Store.IsReady,
            total = plugin.Store.RowCount(),
        });
    }
}
