# Work & contracts (actions) - 11 populated

Point-in-time capture: Eco via Sirens, cycle 13 day 56 (2026-06-12). Action datasets have row-level CSV exporters at `/api/v1/exporter/actions?actionName=<name>`; series come from `/datasets/get` as daily samples. Format: `* name - rows (csv) / points with data - latest / peak`. Part of the pull-everything survey, [#7](https://forgejo.coilysiren.me/coilyco-gaming/eco-app/issues/7).

* LaborWorkOrderAction - 3,362 csv rows / 57/57 daily pts - latest 10, peak 2,983 ActionsPerHour
* CreateWorkOrder - 3,318 csv rows / 57/57 daily pts - latest 5, peak 1,344 ActionsPerHour
* WorkedForWorkParty - 82 csv rows / 30/57 daily pts - latest 0, peak 362 ActionsPerHour
* CompletedWorkParty - 50 csv rows / 21/57 daily pts - latest 0, peak 4 ActionsPerHour
* PostedWorkParty - 46 csv rows / 30/57 daily pts - latest 0, peak 5 ActionsPerHour
* JoinedWorkParty - 35 csv rows / 25/57 daily pts - latest 0, peak 6 ActionsPerHour
* JoinedContract - 16 csv rows / 14/57 daily pts - latest 0, peak 3 ActionsPerHour
* CompletedContract - 7 csv rows / 5/57 daily pts - latest 0, peak 3 ActionsPerHour
* FailedContract - 6 csv rows / 6/57 daily pts - latest 0, peak 5 ActionsPerHour
* PostedContract - 5 csv rows / 3/57 daily pts - latest 0, peak 7 ActionsPerHour
* LeftWorkParty - 1 csv rows / 1/57 daily pts - latest 0, peak 1 ActionsPerHour
