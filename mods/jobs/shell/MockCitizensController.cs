using EcoJobsTracker;
using Microsoft.AspNetCore.Mvc;

namespace EcoJobsTracker.Shell;

// Same route as the real mod with canned data, so a consumer can join exporter
// citizen ids to names against a live C# server without booting Eco. Ids are
// the six-digit shape the real exporter emits; names line up with the mock
// skills roster. See eco-app#5.
[ApiController]
[Route("api/v1/citizens")]
public class MockCitizensController : ControllerBase
{
    [HttpGet]
    public IEnumerable<CitizenDto> Get()
    {
        return new[]
        {
            new CitizenDto(129312, "coilysiren"),
            new CitizenDto(130409, "ekans"),
            new CitizenDto(129580, "redwood"),
            new CitizenDto(129558, "salt"),
            new CitizenDto(4478, "hammerhand"),
        };
    }
}
