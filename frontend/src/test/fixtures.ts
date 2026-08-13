import type { EcoStatus } from "../lib/api"

export const SAMPLE_STATUS: EcoStatus = {
  view: "eco_status",
  fetchedAtISO: "2026-06-12T11:46:33+00:00",
  sourceUrl: "http://example.test:3001/info",
  server: {
    description: "<color=green>Eco</color> via <color=blue>Sirens</color> | Cycle 13",
    detailedDescription: "Cycle 13.",
    category: "Established",
    discord: "https://discord.gg/example",
    version: "0.13.0.4 beta release-1024",
    language: "English",
    paused: false,
    hasPassword: false,
    adminOnline: false,
  },
  players: {
    online: 1,
    onlineNames: ["coilysiren"],
    total: 114,
    activeAndOnline: 4,
    peakActive: 38,
  },
  world: {
    size: "0.52km²",
    plants: 64342,
    animals: 0,
    laws: 10,
    totalCulture: 2254.76,
    totalCultureSource: "info",
  },
  cycle: {
    daysRunning: 56,
    daysUntilMeteor: 3,
    // 56 in-game days + 12 in-game hours: 56 * 3600 + 1800 = 203400s.
    timeSinceStartS: 203400,
    hasMeteor: true,
    collaboration: "HighCollaboration",
    gameSpeed: "Slow",
    simulationLevel: "Normal",
  },
  economy: { description: "1341 trades, 0 contracts" },
  achievements: [],
}
