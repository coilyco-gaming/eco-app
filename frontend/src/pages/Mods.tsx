import Layout from "../components/Layout"

const FORGE_ROOT = "https://forgejo.coilysiren.me/coilyco-gaming/eco-app/src/branch/main/"

interface ModDoc {
  name: string
  packageName: string
  summary: string
  powers: string
  surface: string[]
  sourceHref: string
  sourceLabel: string
  operationsHref?: string
  operationsLabel?: string
  limitation: string
}

// This is intentionally a flat, static reference rather than a status page:
// package contents and server plugins are released independently of the SPA.
// Every claim below comes from the tracked docs and project files linked here.
const MODS: ModDoc[] = [
  {
    name: "Jobs Tracker",
    packageName: "eco-jobs-tracker",
    summary: "Exports the server's learned specialties and citizen-name mapping.",
    powers: "Powers the Jobs roster and the citizen-name joins used by the crafting atlas.",
    surface: ["GET /api/v1/skills", "GET /api/v1/citizens", "SPA: /jobs and /crafting"],
    sourceHref: `${FORGE_ROOT}mods/jobs/README.md`,
    sourceLabel: "Jobs Tracker source and API notes",
    limitation:
      "Its scope is current learned specialties plus the citizen lookup; it is not a skill-history recorder.",
  },
  {
    name: "Replay",
    packageName: "eco-replay",
    summary: "Records every Eco GameAction into a SQLite event log for read-only playback.",
    powers: "Powers the Kaihronicler replay API and the site's read-only /replay timeline.",
    surface: [
      "GET /api/v1/events and /api/v1/events/stats",
      "SQLite: Storage/EcoReplay.db",
      "SPA/API: /replay and /replay/api/v1/*",
    ],
    sourceHref: `${FORGE_ROOT}docs/replay/README.md`,
    sourceLabel: "Replay source and API notes",
    limitation:
      "Action bodies are best-effort, structurally bounded snapshots (including a 16 KB cap), so they are not a full game-state archive.",
  },
  {
    name: "Store Exporter",
    packageName: "eco-store-exporter",
    summary: "Reads live store shelves and per-currency account balances inside Eco.",
    powers:
      "Makes the Trade directory, logistics decisions, watchers, and currency top-holder reports shelf-accurate instead of history-derived.",
    surface: [
      "GET /api/v1/stores",
      "GET /api/v1/currency-holdings",
      "SPA/data: /trade, /preview/stores.json, /preview/logistics.json, and /preview/currency.json",
    ],
    sourceHref: `${FORGE_ROOT}mods/stores/README.md`,
    sourceLabel: "Store Exporter source and API notes",
    operationsHref: `${FORGE_ROOT}mods/stores/docs/dto.md`,
    operationsLabel: "Store response contract",
    limitation:
      "Its reflection-based scans are deliberately null-tolerant: Eco API drift or orphaned objects can yield a partial or empty response rather than a failed build.",
  },
  {
    name: "Telemetry",
    packageName: "eco-telemetry",
    summary: "Sends Eco logs, exceptions, runtime/game metrics, and traces to OTLP backends.",
    powers:
      "Provides the live climate-rules endpoint behind the World page's climate overlay; its other signals serve server operations.",
    surface: [
      "GET /api/v1/climate-settings",
      "OTLP logs, metrics, and traces",
      "SPA/data: /map and /preview/get_eco_climate.json",
    ],
    sourceHref: `${FORGE_ROOT}mods/telemetry/README.md`,
    sourceLabel: "Telemetry source and configuration",
    operationsHref: `${FORGE_ROOT}mods/telemetry/docs/operations.md`,
    operationsLabel: "Telemetry operations notes",
    limitation:
      "v0.1.0 is early: broad request-pipeline hooks and PluginManager-wide init spans are not implemented; unreadable climate settings return 404 and the site falls back per field.",
  },
]

export default function Mods() {
  return (
    <Layout>
      <section className="hero hero-compact">
        <h1 className="hero-title">
          The C# <span className="accent">mods</span> behind the site
        </h1>
        <p className="hero-tagline">
          Four production Eco server plugins provide the live surfaces this site reads. This page is
          a public map of their contracts, packages, and boundaries.
        </p>
      </section>

      <section className="mod-docs" aria-label="production C# mods">
        {MODS.map((mod) => (
          <article className="mod-doc" key={mod.packageName} data-testid={`mod-${mod.packageName}`}>
            <header className="mod-doc-heading">
              <div>
                <h2>{mod.name}</h2>
                <p>{mod.summary}</p>
              </div>
              <code>{mod.packageName}</code>
            </header>

            <dl className="mod-doc-details">
              <div>
                <dt>Powers</dt>
                <dd>{mod.powers}</dd>
              </div>
              <div>
                <dt>API and data surface</dt>
                <dd>
                  <ul>
                    {mod.surface.map((item) => (
                      <li key={item}>{item}</li>
                    ))}
                  </ul>
                </dd>
              </div>
              <div>
                <dt>Install-ready package</dt>
                <dd>
                  CI publishes the immutable <code>{mod.packageName}</code> Forgejo generic package.
                  Select its <code>&lt;version&gt;+&lt;commit&gt;</code> release ZIP, verify the included
                  checksum, extract it into the Eco server&apos;s <code>Mods/</code> directory, then restart
                  Eco.
                </dd>
              </div>
              <div>
                <dt>Eco coupling and current limit</dt>
                <dd>
                  Targets <code>net10.0</code> and Eco.ReferenceAssemblies <code>0.13.0.4-beta-release-1024</code>;
                  compatibility across other Eco builds is not guaranteed. {mod.limitation}
                </dd>
              </div>
            </dl>

            <p className="mod-doc-links">
              <a href={mod.sourceHref}>{mod.sourceLabel} ↗</a>
              {mod.operationsHref && mod.operationsLabel && (
                <>
                  <span aria-hidden="true"> · </span>
                  <a href={mod.operationsHref}>{mod.operationsLabel} ↗</a>
                </>
              )}
              <span aria-hidden="true"> · </span>
              <a href="https://forgejo.coilysiren.me/coilyco-gaming/eco-app/src/branch/main/docs/mod-packages.md">
                Package contract ↗
              </a>
            </p>
          </article>
        ))}
      </section>
    </Layout>
  )
}
