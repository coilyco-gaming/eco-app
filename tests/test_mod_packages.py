from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

from scripts.mod_packages import ModProject, package_mods


def test_package_mods_creates_deterministic_install_archive(tmp_path: Path) -> None:
    project = tmp_path / "mods" / "sample" / "SampleMod.csproj"
    project.parent.mkdir(parents=True)
    project.write_text(
        """<Project Sdk="Microsoft.NET.Sdk">
  <PropertyGroup>
    <TargetFramework>net10.0</TargetFramework>
    <AssemblyName>SampleMod</AssemblyName>
    <Version>1.2.3</Version>
  </PropertyGroup>
  <ItemGroup>
    <PackageReference Include="Eco.ReferenceAssemblies" Version="1.0.0" />
  </ItemGroup>
</Project>
""",
        encoding="utf-8",
    )
    build_output = project.parent / "bin" / "Release" / "net10.0"
    native_output = build_output / "runtimes" / "linux-x64" / "native"
    native_output.mkdir(parents=True)
    (build_output / "SampleMod.dll").write_bytes(b"assembly")
    (build_output / "SampleMod.deps.json").write_text("{}\n", encoding="utf-8")
    (native_output / "libsample.so").write_bytes(b"native")

    output = tmp_path / "packages"
    package_mods(tmp_path, output, "abc123")
    archive = output / "SampleMod-1.2.3.zip"
    first_digest = hashlib.sha256(archive.read_bytes()).hexdigest()

    package_mods(tmp_path, output, "abc123")

    assert hashlib.sha256(archive.read_bytes()).hexdigest() == first_digest
    with zipfile.ZipFile(archive) as package:
        assert package.namelist() == [
            "Mods/SampleMod/SampleMod.deps.json",
            "Mods/SampleMod/SampleMod.dll",
            "Mods/SampleMod/runtimes/linux-x64/native/libsample.so",
        ]

    manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["source_revision"] == "abc123"
    assert manifest["packages"][0]["package_name"] == "sample-mod"
    assert manifest["packages"][0]["registry_version"] == "1.2.3+abc123"
    assert manifest["packages"][0]["checksum"] == first_digest


def test_package_name_splits_assembly_words() -> None:
    project = ModProject(Path("Sample.csproj"), "EcoJobsTracker", "1.0.0", "net10.0")

    assert project.package_name == "eco-jobs-tracker"
