using Eco.Gameplay.Players;
using static EcoStoreExporter.Reflect;

namespace EcoStoreExporter;

// Walks live economy state and, per currency, exports the top account balances -
// the one piece of DiscordLink's `Currency <name>` that trade history cannot
// reconstruct (eco-app#58). `PersonalWealthInDefaultCurrency` is a single
// aggregate series and `CurrencyTrade` rows are flows, not balances; only the
// in-process `CurrencyManager` carries per-account, per-currency holdings.
//
// Why almost-all reflection, unlike the typed CurrencyManager API? Same two
// reasons StoreScanner documents, sharpened by the fact that this mod's ONLY CI
// signal is the compile gate and its NuGet egress is flaky:
//
//  1. API drift. The Eco.Gameplay.Economy graph (CurrencyManager, Currency,
//     BankAccount, CurrencyHolding) renames and moves members across beta
//     releases. Reaching every economy member by name via Reflect.FindType /
//     GetStaticMember / GetMember means the mod keeps COMPILING regardless of
//     that drift - a wrong guess degrades to an empty response, it never breaks
//     the build. Taking a compile-time dependency on, say, CurrencyManager.Currencies
//     would fail the gate the day that member is renamed.
//
//  2. Dangling references. Orphaned accounts and currencies removed by a mod
//     update can survive a save migration (the gaming-eco-investigation case
//     library). Every hop is null- and exception-guarded and skips-and-continues.
//
// The ONE typed touchpoint is `UserManager` (Eco.Gameplay.Players) for the
// id->name join, exactly as mods/jobs' CitizensApiController uses it and as
// StoreScanner uses the stable `WorldObjectManager`. A partial holdings table is
// the correct answer; a 500 is not. Contract: docs/currency-holdings.md.
public static class CurrencyHoldingsScanner
{
    // Per-currency truncation. DiscordLink shows a handful; we export a deeper
    // slice so the Python report can re-rank/re-cap. Totals below are over ALL
    // accounts, so truncation here never distorts the money-supply figure.
    private const int TopHoldersCap = 25;

    // Fully-qualified economy type names, tried in order. The assembly they live
    // in is not assumed - Reflect.FindType scans every loaded assembly.
    private static readonly string[] CurrencyManagerTypes =
    {
        "Eco.Gameplay.Economy.CurrencyManager",
        "Eco.Gameplay.Economy.Money.CurrencyManager",
    };

    private static readonly string[] BankAccountManagerTypes =
    {
        "Eco.Gameplay.Economy.BankAccountManager",
        "Eco.Gameplay.Economy.Money.BankAccountManager",
    };

    private static readonly string[] BankAccountTypes =
    {
        "Eco.Gameplay.Economy.BankAccount",
        "Eco.Gameplay.Economy.Money.BankAccount",
    };

    public static List<CurrencyHoldingsDto> Scan()
    {
        try
        {
            var names = BuildUserNameMap();

            // Currency ref -> accumulator. Reference identity keys holdings back
            // to the same Currency object the manager listed, even when two
            // currencies share a display name.
            var byCurrency = new Dictionary<object, CurrencyAcc>(ReferenceEqualityComparer.Instance);

            // Seed from the manager's currency roster so a currency with zero
            // holdings still appears (empty holder list, zero totals).
            foreach (var currency in EnumerateCurrencies())
            {
                Acc(byCurrency, currency);
            }

            // Fold every account's holdings into the accumulators.
            foreach (var account in EnumerateAccounts())
            {
                FoldAccount(account, names, byCurrency);
            }

            var result = new List<CurrencyHoldingsDto>(byCurrency.Count);
            foreach (var acc in byCurrency.Values)
            {
                result.Add(acc.Build(TopHoldersCap));
            }

            // Richest currencies first, matching how the roster surfaces "top".
            result.Sort((a, b) => b.TotalHoldings.CompareTo(a.TotalHoldings));
            return result;
        }
        catch
        {
            // CurrencyManager unready during early init, or the whole economy
            // graph moved. Best-effort: an empty list, never a 500.
            return new List<CurrencyHoldingsDto>();
        }
    }

    // --- currencies -----------------------------------------------------------

    private static IEnumerable<object> EnumerateCurrencies()
    {
        var manager = FindType(CurrencyManagerTypes);
        var currencies = GetStaticMember(manager, "Currencies", "AllCurrencies", "ActiveCurrencies");
        return AsSequence(currencies);
    }

    private static CurrencyAcc Acc(Dictionary<object, CurrencyAcc> map, object currency)
    {
        if (!map.TryGetValue(currency, out var acc))
        {
            acc = new CurrencyAcc(
                name: AsString(GetMember(currency, "Name", "MarkupName", "DisplayName")) ?? "Unknown Currency",
                // The join key the action exporter writes into CurrencyTrade
                // rows. See CurrencyHoldingsDto.Id and eco-app#217.
                id: AsString(GetMember(currency, "Id", "CurrencyId", "ObjectId")),
                backed: ReadBacked(currency));
            map[currency] = acc;
        }

        return acc;
    }

    private static bool? ReadBacked(object currency)
    {
        var direct = AsBool(GetMember(currency, "Backed", "IsBacked"));
        if (direct is not null) return direct;

        // MoneyType is an enum on Eco's Currency: minted/backed vs personal/credit.
        var moneyType = AsString(GetMember(currency, "MoneyType", "CurrencyType"));
        if (moneyType is not null)
        {
            var lowered = moneyType.ToLowerInvariant();
            if (lowered.Contains("back") || lowered.Contains("mint")) return true;
            if (lowered.Contains("personal") || lowered.Contains("credit")) return false;
        }

        // A backing item present at all means it is a backed currency.
        if (GetMember(currency, "BackingItem", "Backing") is not null) return true;

        return null;
    }

    // --- accounts -------------------------------------------------------------

    private static IEnumerable<object> EnumerateAccounts()
    {
        // Strategy 1: the currency manager itself may expose the account list.
        var manager = FindType(CurrencyManagerTypes);
        var fromManager = GetStaticMember(manager, "Accounts", "AllAccounts", "BankAccounts");
        var seq = AsSequence(fromManager).ToList();
        if (seq.Count > 0) return seq;

        // Strategy 2: a dedicated BankAccountManager singleton.
        var bamType = FindType(BankAccountManagerTypes);
        var bamObj = GetStaticMember(bamType, "Obj", "Instance", "Manager");
        var fromBam = GetMember(bamObj, "Accounts", "AllAccounts", "BankAccounts")
                      ?? GetStaticMember(bamType, "Accounts", "AllAccounts", "BankAccounts");
        seq = AsSequence(fromBam).ToList();
        if (seq.Count > 0) return seq;

        // Strategy 3: the generic registrar, Registrars.Get<BankAccount>().
        var registrars = FindType("Eco.Core.Systems.Registrars", "Eco.Shared.Systems.Registrars");
        var accountType = FindType(BankAccountTypes);
        var fromRegistrar = InvokeStaticGeneric(registrars, accountType, "Get", "All", "GetAll");
        return AsSequence(fromRegistrar).ToList();
    }

    private static void FoldAccount(object account, Dictionary<int, string> names, Dictionary<object, CurrencyAcc> byCurrency)
    {
        try
        {
            var accountName = AsString(GetMember(account, "Name", "MarkupName", "DisplayName")) ?? "Bank Account";
            var holder = ResolveHolder(account, names);

            // BankAccount.CurrencyHoldings is a ControllerDictionary<Currency,
            // CurrencyHolding>. Enumerating it directly yields KeyValuePairs, so
            // prefer its `.Values` (the CurrencyHolding objects). Fall back to a
            // plain-list accessor for any Eco version that exposes one instead.
            var holdingsObj = GetMember(account, "CurrencyHoldings", "Holdings", "CurrencyHolding")
                              ?? Invoke(account, "GetCurrencyHoldings");
            var holdings = GetMember(holdingsObj, "Values") ?? holdingsObj;

            foreach (var raw in AsSequence(holdings))
            {
                try
                {
                    // A CurrencyHolding exposes `.Currency` directly; a dictionary
                    // KeyValuePair (the fallback path) carries it under `.Value`.
                    var holding = GetMember(raw, "Currency") is not null ? raw : GetMember(raw, "Value") ?? raw;

                    var currency = GetMember(holding, "Currency");
                    if (currency is null) continue;

                    var val = AsDouble(GetMember(holding, "Val", "Amount", "Value", "HoldingVal", "Balance"));
                    if (val is null || val.Value <= 0) continue; // skip zero/negative dust

                    Acc(byCurrency, currency).Add(accountName, holder, val.Value);
                }
                catch
                {
                    // A holding whose Currency reference dangles. Skip it.
                }
            }
        }
        catch
        {
            // Orphaned account. Skip it rather than sink the whole export.
        }
    }

    // The account's owning citizen name, joined via UserManager where the
    // account only yields a numeric user id. Null for accounts with no single
    // owner (government/company accounts) - the account name carries those.
    private static string? ResolveHolder(object account, Dictionary<int, string> names)
    {
        // AccountOwner is Eco's single-owner accessor (null for government/company
        // accounts); Creator/AnyUser are best-effort fallbacks.
        var owner = GetMember(account, "AccountOwner", "Creator", "OwnerUser", "Owner", "AnyUser", "Player");
        if (owner is null) return null;

        var direct = AsString(GetMember(owner, "Name", "DisplayName", "MarkupName"));
        if (direct is not null) return direct;

        var id = AsInt(GetMember(owner, "Id", "UserId"));
        if (id is not null && names.TryGetValue(id.Value, out var name)) return name;

        return null;
    }

    // --- user id -> name join (the one typed touchpoint) ----------------------

    private static Dictionary<int, string> BuildUserNameMap()
    {
        var map = new Dictionary<int, string>();
        try
        {
            foreach (var user in UserManager.Users)
            {
                if (user is null) continue;
                if (!string.IsNullOrWhiteSpace(user.Name)) map[user.Id] = user.Name;
            }
        }
        catch
        {
            // UserManager unready during early init. Fall back to account names.
        }

        return map;
    }

    // Mutable per-currency accumulator, materialized into a CurrencyHoldingsDto.
    private sealed class CurrencyAcc
    {
        private readonly string name;
        private readonly string? id;
        private readonly bool? backed;
        private readonly List<HolderDto> holders = new();
        private int accountsCounted;
        private double totalHoldings;

        public CurrencyAcc(string name, string? id, bool? backed)
        {
            this.name = name;
            this.id = id;
            this.backed = backed;
        }

        public void Add(string account, string? holder, double balance)
        {
            this.accountsCounted++;
            this.totalHoldings += balance;
            this.holders.Add(new HolderDto(account, holder, balance));
        }

        public CurrencyHoldingsDto Build(int cap)
        {
            this.holders.Sort((a, b) => b.Balance.CompareTo(a.Balance));
            var top = this.holders.Count > cap ? this.holders.GetRange(0, cap) : this.holders;
            return new CurrencyHoldingsDto(
                this.name,
                this.id,
                this.backed,
                this.accountsCounted,
                this.totalHoldings,
                top.ToArray());
        }
    }
}
