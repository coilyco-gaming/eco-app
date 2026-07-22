# Eco mod packages

eco-app builds its in-process Eco server plugins as part of the application
image build. The resulting ZIPs are install-ready Forgejo generic packages and
the source artifacts for later mod.io promotion.

## Build contract

The Dockerfile's `mods` stage uses the same pinned agentic-os release as the
rest of the image, selecting the `lang-dotnet` tier. The stage discovers every
project under `mods/` that references `Eco.ReferenceAssemblies`, restores it,
builds it in `Release`, and packages the complete build output.

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
CI extracts that directory from the already-built image. It never recompiles
the mods outside the image or publishes a different copy.

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
build. A repeated workflow run for the same commit is idempotent. The publisher
accepts an existing file only when its checksum matches the local file.

Forgejo owns generic packages at the organization level. CI publishes under
`coilyco-gaming` and authenticates as `coilyco-ops` with the
`ECO_MOD_PACKAGE_TOKEN` Actions secret. The workflow exposes it to the
publisher as `FORGEJO_PACKAGE_TOKEN`; the token needs only the `write:package`
scope.

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

## mod.io promotion and eco-mods

Future mod.io automation should download the ZIP and metadata from Forgejo,
verify the SHA-256 checksum, and upload those exact bytes. It should never run
`dotnet build` again. The project's source version becomes the mod.io file
version, while the Forgejo version and metadata preserve the exact source
commit.

The sibling `coilyco-gaming/eco-mods` repo can adopt the same contract:

* discover real mod projects from the `Eco.ReferenceAssemblies` reference
* read `AssemblyName`, `Version`, and `TargetFramework` from each project
* package under `Mods/<AssemblyName>/`
* publish immutable `<Version>+<commit>` generic package versions
* promote checksum-verified Forgejo archives to mod.io

This keeps repository-specific compilation in each repository while giving the
eventual mod.io publisher one artifact and metadata schema to consume.
