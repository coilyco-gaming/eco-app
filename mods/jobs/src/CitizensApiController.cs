using Eco.Gameplay.Players;
using Microsoft.AspNetCore.Mvc;

namespace EcoJobsTracker;

// Lives inside the Eco server process. Exposes the numeric in-game user id ->
// display name join the action exporter needs: the exporter keys its Citizen
// column by a bare numeric id, and only in-process UserManager access can map
// that id back to a name (the admin /api/v1/users surface omits it). The
// crafting atlas consumes this to attribute production by citizen. See
// eco-app#5.
[ApiController]
[Route("api/v1/citizens")]
public class CitizensApiController : ControllerBase
{
    [HttpGet]
    public IEnumerable<CitizenDto> Get()
    {
        return UserManager.Users.Select(user => new CitizenDto(user.Id, user.Name));
    }
}
