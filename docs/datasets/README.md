# Live dataset survey - per-type files

Point-in-time capture: Eco via Sirens, cycle 13 day 56 (2026-06-12). Action datasets have row-level CSV exporters at `/api/v1/exporter/actions?actionName=<name>`; series come from `/datasets/get` as daily samples. Format: `* name - rows (csv) / points with data - latest / peak`. Part of the pull-everything survey, [#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7).

* [Commerce & money (actions)](actions-commerce.md) - 15
* [Civics & settlement (actions)](actions-civics.md) - 14
* [Social (actions)](actions-social.md) - 4
* [Progression (actions)](actions-progression.md) - 4
* [Work & contracts (actions)](actions-work.md) - 11
* [Industry & world mutation (actions)](actions-industry.md) - 20
* [Economy (series)](series-economy.md) - 3
* [Civics & people (series)](series-civics.md) - 10
* [Progression (series)](series-progression.md) - 3
* [Climate & atmosphere (series)](series-climate.md) - 7
* [Flora populations (series)](series-flora.md) - 68
* [Fauna populations (series)](series-fauna.md) - 26
* [World & misc (series)](series-world.md) - 7

Empty-this-cycle datasets are listed in the issue, not here, per review scope.
