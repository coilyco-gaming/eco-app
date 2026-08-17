"""Local dev harness: snapshot the eco server's data sources and replay them.

Three moving parts, composed by the Ward `snapshot-*` verbs:

1. `capture` (capture.py) - pull every upstream endpoint the app consumes
   (info, dataset catalog + every series, every action CSV, species CSVs,
   civics, map layers, jobs/citizens/stores/replay mod surfaces) into a
   snapshot directory, byte-for-byte, indexed by `manifest.json`.
2. S3 push/pull - the Ward command dispatcher tars the snapshot dir to
   `s3://kai-game-backups/eco-app/snapshots/` and pulls it back, so any
   machine can iterate against a real capture without touching the live
   game server.
3. `serve` (serve.py) - a fixture server that replays the manifest on
   localhost. Point `ECO_INFO_URL` at it (`just http-offline`) and the
   fused app runs fully offline.
"""
