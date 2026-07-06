using Eco.Gameplay.Players;
using Eco.Shared.Time;
using Microsoft.AspNetCore.Mvc;

namespace EcoJobsTracker;

// Lives inside the Eco server process. Eco's ASP.NET Core host picks up
// [ApiController] classes from mod assemblies via AddApplicationPart.
[ApiController]
[Route("api/v1/skills")]
public class SkillsApiController : ControllerBase
{
    [HttpGet]
    public IEnumerable<PlayerSkillsDto> Get()
    {
        var nowUtc = DateTime.UtcNow;
        var nowGameSeconds = TimeUtil.Seconds;

        return UserManager.Users.Select(user =>
        {
            var specialties = user.Skillset.Skills
                .Where(skill => skill.Level > 0 && skill.IsSpecialty)
                .Select(skill => new SpecialtyDto(
                    skill.DisplayName,
                    skill.Level,
                    skill.MaxLevel))
                .ToArray();

            // Anchor "last seen" to wall-clock. Eco stores per-user times in
            // WorldTime seconds (the TimeUtil.Seconds domain), so convert the
            // elapsed game-seconds back to real time. The active-in-N-days bucket
            // the Python tracker derives absorbs the sub-day rounding.
            //
            // Use LastOnlineTime, which Eco persists across server restarts, as
            // the anchor. LogoutTime is only populated for a logout that happened
            // in the current server session, so after a restart it reads 0 for
            // every player not currently connected - which collapsed all offline
            // players to "never seen" and left only currently-online players
            // counting as active. That is the "online, not active" bug in
            // eco-app#76. LogoutTime stays as a secondary anchor in case a build
            // reports it but not LastOnlineTime; we take whichever is newer.
            string? lastSeen = null;
            if (user.LoggedIn)
            {
                lastSeen = nowUtc.ToString("yyyy-MM-ddTHH:mm:ssZ");
            }
            else
            {
                var seenGameSeconds = Math.Max(user.LastOnlineTime, user.LogoutTime);
                if (seenGameSeconds > 0)
                {
                    // Clamp to >= 0: a slightly-ahead persisted stamp must never
                    // yield a future lastSeen (which would read as trivially active).
                    var ago = TimeSpan.FromSeconds(Math.Max(0, nowGameSeconds - seenGameSeconds));
                    lastSeen = (nowUtc - ago).ToString("yyyy-MM-ddTHH:mm:ssZ");
                }
            }

            return new PlayerSkillsDto(user.Name, lastSeen, specialties);
        });
    }
}
