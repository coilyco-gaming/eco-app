# Eco mod packages

eco-app builds its in-process Eco server plugins as part of the application
image build. The resulting ZIPs are install-ready Forgejo generic packages and
the source artifacts for later mod.io promotion.

## Build contract

The Dockerfile's `mods` stage uses the same moving `agentic-os:release` full
image as the rest of the build. The stage discovers every project under `mods/`
that references `Eco.ReferenceAssemblies`, restores it, builds it in `Release`,
and packages the complete build output.

Each archive has this layout:

```text
Mods/
└── <AssemblyName>/
    ├── <AssemblyName>.dll
    ├── <AssemblyName>.deps.json
    └── <runtime dependencies>
```

The packager preserves nested runtime directories, which matters for mods such
as EcoReplay and EcoTelemetry that ship dependencies beyond their primary DLL.
ZIP timestamps, file order, and permissions are normalized so identical build
outputs produce identical archives.

The final application image carries the generated files at `/mod-packages`.
CI builds and pushes that image once, then starts one matrix task for each mod.
Every task pulls the already-built image, extracts that directory, and publishes
only its assigned manifest record. No publisher recompiles a mod or publishes a
different copy.

## Required CI policy

The application image build is the required C# compile gate. It discovers every
real Eco mod project, restores and builds each project once, and fails on the
first broken restore or compile phase. Keeping compilation together is
deliberate: the shipped application image contains one coherent set of mod
packages from one source revision.

Publication fans out after that shared build. One independent matrix task
publishes each package, with fail-fast disabled so a registry failure for one
mod does not hide the status of the others. The build-image job has a 30-minute
timeout and each publisher has a 20-minute timeout. Those bounds leave room for
the normal proxied NuGet and image-transfer path while preventing a stalled
restore, Docker operation, or upload from becoming an indefinite CI sink.

## Versions and registry coordinates

The source version is each project's `<Version>` property. A main-branch build
publishes an immutable Forgejo package version with the source commit appended:

```text
<mod-version>+<full-git-sha>
```

Package names are the kebab-case assembly names. For example,
`EcoJobsTracker` becomes `eco-jobs-tracker`. Each package version contains:

* `<AssemblyName>-<mod-version>.zip` - the install-ready archive
* `<AssemblyName>-<mod-version>.json` - source, framework, version, and checksum metadata
* `<AssemblyName>-<mod-version>.zip.sha256` - the archive checksum

`.build/mod-packages/manifest.json` indexes every package emitted by one image
build. `MOD_PACKAGE_NAME` selects one record for a matrix task; leaving it unset
preserves the local all-packages command. A repeated workflow run for the same
commit is idempotent. The publisher accepts an existing file only when its
checksum matches the local file.

Forgejo owns generic packages at the organization level. CI publishes under
`coilyco-gaming` and authenticates as `coilyco-ops` with the
`ECO_MOD_PACKAGE_TOKEN` Actions secret. The workflow exposes it to the
publisher as `FORGEJO_PACKAGE_TOKEN`; the token needs only the `write:package`
scope.

The `build-image` job receives `FORGEJO_EGRESS_PROXY` from the infrastructure-
owned Forgejo runner. CI passes that value only as Docker's predefined
`HTTP_PROXY` and `HTTPS_PROXY` build arguments, which route the multi-stage
dependency restores without persisting the proxy address in the application
image. The allowlist and live verification procedure live in infrastructure's
`docs/forgejo-runner-egress-proxy.md`.

## Commands

```text
ward exec build-mods
ward exec test-mod-replay
ward exec package-mods
ward exec build-docker
```

`ward exec publish-mod-packages` is the CI publication boundary. It requires
`FORGEJO_PACKAGE_URL`, `FORGEJO_PACKAGE_OWNER`, `FORGEJO_PACKAGE_USER`, and
`FORGEJO_PACKAGE_TOKEN`. Operators should not place the token in tracked files
or shell history.

## mod.io promotion

`.forgejo/workflows/modio-publish.yml` is a **manual-only** promotion boundary.
It never runs from a push to `main`, never invokes `dotnet`, and never rebuilds
a mod. The operator selects one package and its immutable Forgejo version. The
publisher downloads that version's published per-package metadata manifest,
checksum sidecar, and ZIP from Forgejo Packages, requiring all three SHA-256
values and the archive name to agree before mod.io is contacted. The exact ZIP
bytes are then uploaded.

The project's source `<Version>` becomes the mod.io file version. The Forgejo
`<Version>+<commit>` coordinate remains the provenance identifier and is
recorded with the source revision and SHA-256 in the mod.io file metadata.

### Setup and operator flow

Create these Actions secrets; do not put their values, mod.io IDs, or tokens
in tracked files:

* `ECO_MOD_PACKAGE_TOKEN` - Forgejo token with `read:package` for the published
  source package (the existing package publisher uses the same secret with
  write scope).
* `MODIO_ACCESS_TOKEN` - mod.io bearer token for an account allowed to upload
  files to the chosen mod.

In Forgejo Actions, run **modio-publish** with:

1. `package`, the exact immutable `registry_version`, and the exact ZIP
   `archive_name` from Forgejo Packages.
2. The target `modio_game_id` and `modio_mod_id`; neither ID is stored here.
3. Release notes, which become the mod.io changelog. Leave `dry_run` enabled
   first to prove the package manifest and ZIP checksum without contacting
   mod.io. `modio_file_id` is optional and is useful when retrying a known
   upload: it must resolve to the same source version and MD5.
4. Re-run with `dry_run` disabled only after that verification passes.

The publisher first checks mod.io for the source file version. A matching MD5
is a successful no-op, so a timeout after a completed upload can be retried
safely. The same version with different bytes fails loudly and is never
overwritten. A failed or rejected upload leaves the Forgejo package untouched;
fix the target/configuration and dispatch the same immutable package again.
mod.io's normal rollback is to select an earlier accepted file as the active
release in its dashboard (or with its file-edit API); this workflow does not
delete or mutate prior releases.

The separate workflow means normal main builds and package publication remain
independent of mod.io availability.

## eco-mods

The sibling `coilyco-gaming/eco-mods` repo can adopt the same contract:

* discover real mod projects from the `Eco.ReferenceAssemblies` reference
* read `AssemblyName`, `Version`, and `TargetFramework` from each project
* package under `Mods/<AssemblyName>/`
* publish immutable `<Version>+<commit>` generic package versions
* promote checksum-verified Forgejo archives to mod.io

This keeps repository-specific compilation in each repository while giving the
eventual mod.io publisher one artifact and metadata schema to consume.
