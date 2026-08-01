import Layout from "../components/Layout"

interface CatalogMod {
  name: string
  summary: string
  href?: string
  source: string
  testId: string
}

const APP_ROOT = "https://forgejo.coilysiren.me/coilyco-gaming/eco-app/src/branch/main/"
const PUBLIC_ROOT = "https://forgejo.coilysiren.me/coilyco-gaming/eco-mods/src/branch/main/"
const NID_TOOLBOX = "https://mod.io/g/eco/m/nidtoolbox-full-pack"

const APP_PLUGINS: CatalogMod[] = [
  {
    name: "Jobs Tracker",
    summary: "Exports learned specialties and citizen names for Jobs and Crafting.",
    href: `${APP_ROOT}mods/jobs/README.md`,
    source: "eco-app source",
    testId: "app-jobs",
  },
  {
    name: "Replay",
    summary: "Records bounded Eco actions for the read-only Kaihronicler timeline.",
    href: `${APP_ROOT}docs/replay/README.md`,
    source: "eco-app source",
    testId: "app-replay",
  },
  {
    name: "Store Exporter",
    summary: "Exports live store shelves and per-currency account balances.",
    href: `${APP_ROOT}mods/stores/README.md`,
    source: "eco-app source",
    testId: "app-stores",
  },
  {
    name: "Telemetry",
    summary: "Exports climate settings and emits Eco logs, metrics, and traces.",
    href: `${APP_ROOT}mods/telemetry/README.md`,
    source: "eco-app source",
    testId: "app-telemetry",
  },
]

const PUBLIC_MODS: CatalogMod[] = [
  {
    name: "BunWulf Agricultural",
    summary: "Extended crops, processing recipes, compost, paper, oils, and crop materials.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/BunWulfAgricultural`,
    source: "public source",
    testId: "public-agricultural",
  },
  {
    name: "BunWulf Biochemical",
    summary: "A plant-based Biochemist path for slower renewable industrial chemistry.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/BunWulfBiochemical`,
    source: "public source",
    testId: "public-biochemical",
  },
  {
    name: "BunWulf Educational",
    summary: "A Librarian profession for skill books, research papers, ink, and paper.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/BunWulfEducational`,
    source: "public source",
    testId: "public-educational",
  },
  {
    name: "BunWulf Hardware Co",
    summary: "Adds the Sledgehammer and Low Tech Streetlamp specialty hardware.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/BunWulfHardwareCo`,
    source: "public source",
    testId: "public-hardware",
  },
  {
    name: "Direct Carbon Capture",
    summary: "A dormant late-game direct-air-capture experiment kept in source.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/DirectCarbonCapture`,
    source: "public source",
    testId: "public-carbon",
  },
  {
    name: "EcoNil",
    summary: "Cloud Seeder and Dehydrator objects for local rainfall and soil moisture control.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/EcoNil`,
    source: "public source",
    testId: "public-econil",
  },
  {
    name: "Mines & Quarries",
    summary: "Expensive mines, quarries, and pits built around vertical integration.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/MinesQuarries`,
    source: "public source",
    testId: "public-mines",
  },
  {
    name: "Shop Boat",
    summary: "A movable fuelled boat with store, storage, property, and repair behavior.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/ShopBoat`,
    source: "public source",
    testId: "public-shopboat",
  },
  {
    name: "World Counter",
    summary: "A Bookkeeping Desk that counts nearby world blocks and reports totals.",
    href: `${PUBLIC_ROOT}mods/Mods/UserCode/WorldCounter`,
    source: "public source",
    testId: "public-counter",
  },
]

const SERVER_MODS: CatalogMod[] = [
  {
    name: "Alpacacorn's Item Pack",
    summary: "Decorative and practical items from Alpacacorn's pack.",
    href: "https://mod.io/g/eco/m/alpacacorns-item-pack-2",
    source: "mod.io",
    testId: "server-alpacacorn",
  },
  {
    name: "Animal Husbandry Reloaded",
    summary: "Expanded animal husbandry gameplay for Eco 10 and later.",
    href: "https://mod.io/g/eco/m/animal-husbandry-reloaded-v10-compatible",
    source: "mod.io",
    testId: "server-husbandry",
  },
  {
    name: "Beekeeping",
    summary: "Beekeeping profession, items, recipes, and related talents.",
    href: "https://mod.io/g/eco/m/beekeeping",
    source: "mod.io",
    testId: "server-beekeeping",
  },
  {
    name: "CavRn Mods",
    summary: "Discord-distributed vehicle and world-object collection.",
    source: "Discord-only release. No public source page.",
    testId: "server-cavrn",
  },
  {
    name: "DF Easier Shop Cart",
    summary: "DeepFlame's shop-cart usability mod.",
    href: "https://github.com/deepflameNL/eco-EasierShopCart",
    source: "GitHub",
    testId: "server-shopcart",
  },
  {
    name: "Dirt Decomposition",
    summary: "A custom set of dirt decomposition recipes.",
    source: "Custom Sirens mod. No public source page.",
    testId: "server-dirt",
  },
  {
    name: "Easy Mining & Logging",
    summary: "Locally tracked tool overrides from the Easy Mining and Logging mod.",
    href: "https://mod.io/g/eco/m/easy-logging-mining-v11",
    source: "mod.io",
    testId: "server-mining",
  },
  {
    name: "Eco Gnome Mod",
    summary: "Exports the server ruleset consumed by the Eco Gnome calculator.",
    href: "https://github.com/Eco-Gnome/eco-gnome-mod/releases/tag/1.4.0",
    source: "GitHub release",
    testId: "server-gnome",
  },
  {
    name: "Elixr Mods",
    summary: "The installed Elixr full-pack collection.",
    href: "https://mod.io/g/eco/m/elixr-mods",
    source: "mod.io",
    testId: "server-elixr",
  },
  {
    name: "Fishing Reloaded",
    summary: "Expanded fishing, processing, and seafood content.",
    href: "https://mod.io/g/eco/m/fishing-reloaded",
    source: "mod.io",
    testId: "server-fishing",
  },
  {
    name: "Greenhouses",
    summary: "Hydroponics and greenhouse growing content.",
    href: "https://mod.io/g/eco/m/hydroponics-and-greenhouses-v2-eco-10-beta",
    source: "mod.io",
    testId: "server-greenhouses",
  },
  {
    name: "Mixology",
    summary: "Drinks, coffee, cocktails, ingredients, and mixology stations.",
    href: "https://mod.io/g/eco/m/mixology-13-0",
    source: "mod.io",
    testId: "server-mixology",
  },
  {
    name: "Nutrition Mod",
    summary: "Additional nutrition configuration and gameplay rules.",
    href: "https://mod.io/g/eco/m/nutrition-mod",
    source: "mod.io",
    testId: "server-nutrition",
  },
  {
    name: "Pan Drippings",
    summary: "Recipes for filtering and purifying pan drippings.",
    href: "https://mod.io/g/eco/m/pan-drippings",
    source: "mod.io",
    testId: "server-drippings",
  },
  {
    name: "Skills Requirements",
    summary: "Configurable specialty and skill requirements.",
    href: "https://github.com/Thibault-Brocheton/eco-skills-requirements",
    source: "GitHub",
    testId: "server-skills",
  },
  {
    name: "StorageMore",
    summary: "Additional storage capacity and object variants.",
    href: "https://mod.io/g/eco/m/stockagemore-6",
    source: "mod.io",
    testId: "server-storage",
  },
  {
    name: "XP Benefits",
    summary: "Configurable benefits tied to player experience.",
    href: "https://mod.io/g/eco/m/xp-benefits",
    source: "mod.io",
    testId: "server-xp",
  },
  {
    name: "Discord Link",
    summary: "Mighty Moose's Eco and Discord bridge.",
    href: "https://mod.io/g/eco/m/discordlink",
    source: "mod.io",
    testId: "server-discord",
  },
  {
    name: "Mighty Moose Core",
    summary: "The shared runtime dependency bundled with Discord Link.",
    href: "https://github.com/Eco-DiscordLink/EcoDiscordPlugin",
    source: "GitHub",
    testId: "server-moose",
  },
  {
    name: "OpenNutriView",
    summary: "An open nutrition viewer distributed as a managed DLL.",
    href: "https://mod.io/g/eco/m/opennutriview",
    source: "mod.io",
    testId: "server-nutri-view",
  },
  {
    name: "Price Calculator",
    summary: "The Mighty Moose price-calculator DLL in the server bundle.",
    source: "Bundled DLL. No verified public source page.",
    testId: "server-price",
  },
]

const NID_MODULES: CatalogMod[] = [
  ["Core", "Shared runtime and assets for every Nid Toolbox module."],
  ["Clean Server", "Server-cleanup utilities."],
  ["Chat Logger", "Chat logging module retained inside the game-server toolbox."],
  ["IP Logger", "Connection logging module for server operations."],
  ["MOTD", "Message-of-the-day rendering and configuration."],
  ["Player Manager", "Player-management utilities."],
  ["Chat Tags", "Configurable chat tags."],
  ["Laws", "Nid Toolbox law helpers."],
  ["News", "In-game news module."],
  ["Rules", "Server-rules display module."],
  ["Timed Messages", "Scheduled in-game informational messages."],
].map(([name, summary]) => ({
  name,
  summary,
  href: NID_TOOLBOX,
  source: "Nid Toolbox on mod.io",
  testId: `nid-${name.toLowerCase().replaceAll(" ", "-")}`,
}))

function CatalogSection({
  title,
  intro,
  mods,
  testId,
}: {
  title: string
  intro: string
  mods: CatalogMod[]
  testId: string
}) {
  return (
    <section className="mod-catalog" data-testid={testId}>
      <div className="mod-catalog-heading">
        <h2>{title}</h2>
        <p>{intro}</p>
      </div>
      <div className="mod-catalog-grid">
        {mods.map((mod) => (
          <article className="mod-catalog-card" key={mod.testId} data-testid={mod.testId}>
            <h3>{mod.name}</h3>
            <p>{mod.summary}</p>
            {mod.href ? (
              <a href={mod.href} target="_blank" rel="noreferrer">
                {mod.source} ↗
              </a>
            ) : (
              <span className="mod-source-note">{mod.source}</span>
            )}
          </article>
        ))}
      </div>
    </section>
  )
}

export default function Mods() {
  return (
    <Layout>
      <section className="hero hero-compact">
        <h1 className="hero-title">
          The complete <span className="accent">mod catalog</span>
        </h1>
        <p className="hero-tagline">
          A compact, attributed snapshot of eco-app's service plugins, the public eco-mods
          collection, and the Sirens server bundle.
        </p>
        <p className="catalog-note">
          Reviewed 2026-08-01 from the canonical inventories. This is a source inventory,
          not a live server-status probe.
        </p>
      </section>

      <CatalogSection
        title="eco-app service plugins"
        intro="Four read-only server plugins feed the application data planes."
        mods={APP_PLUGINS}
        testId="catalog-app"
      />
      <CatalogSection
        title="Public gameplay mods"
        intro="Nine open source gameplay mods maintained in coilyco-gaming/eco-mods."
        mods={PUBLIC_MODS}
        testId="catalog-public"
      />
      <CatalogSection
        title="Sirens server bundle"
        intro="Third-party and custom inputs used by the Sirens Eco server."
        mods={SERVER_MODS}
        testId="catalog-server"
      />
      <CatalogSection
        title="Nid Toolbox modules"
        intro="The full pack stays separate so each installed module is visible."
        mods={NID_MODULES}
        testId="catalog-nid"
      />
    </Layout>
  )
}
