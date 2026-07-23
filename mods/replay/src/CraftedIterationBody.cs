using Newtonsoft.Json;

namespace EcoReplay;

// Fixed, scalar-only body for ItemCraftedAction. Citizen and both clocks stay
// in EventRow's first-class columns; this contains the craft-specific labels.
// Do not add live Eco objects here: this is deliberately independent of the
// generic reflection serializer used by every other action type.
public static class CraftedIterationBody
{
    public const string Schema = "craft-iteration/v1";

    public static string Serialize(
        string? item,
        string? station,
        string? byproduct,
        string? position)
        => JsonConvert.SerializeObject(new
        {
            schema = Schema,
            item,
            station,
            byproduct,
            position,
            iterations = 1,
        });
}
