from __future__ import annotations

import argparse
import hashlib
import json
import os
import zipfile
from pathlib import Path
from typing import Any


ROOT_FILES = {
    "README.md",
    "install.sh",
    "main.py",
    "requirements.txt",
    "reset_runtime_state.py",
    "update.sh",
}
SOURCE_DIRECTORIES = {
    "docs",
    "hardware",
    "resq_core",
    "scripts",
    "static",
    "system",
    "templates",
    "tests",
    "ui",
}
EXCLUDED_DIRECTORY_NAMES = {
    ".git",
    ".idea",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    ".vscode",
    "__MACOSX",
    "__pycache__",
    "data",
    "dist",
    "logs",
}
EXCLUDED_FILE_NAMES = {
    ".DS_Store",
    ".coverage",
    ".env",
    "id_ed25519",
    "id_rsa",
}
EXCLUDED_SUFFIXES = {
    ".cache",
    ".env",
    ".key",
    ".log",
    ".pem",
    ".pyc",
    ".pyo",
    ".swp",
    ".tmp",
    ".zip",
}
EXCLUDED_RELEASE_PATHS = {
    Path("docs/migration_v0_5.md"),
    Path("resq_core/protocol_loader.py"),
}
FIXED_ZIP_TIMESTAMP = (2020, 1, 1, 0, 0, 0)


class ReleaseBuildError(RuntimeError):
    """Raised when a clean release artifact cannot be produced."""


def build_release(project_root: Path, output_dir: Path | None = None) -> Path:
    project_root = project_root.resolve()
    metadata = _load_release_metadata(project_root)
    artifact_name = str(metadata["artifact_name"])
    if Path(artifact_name).name != artifact_name or not artifact_name.endswith(".zip"):
        raise ReleaseBuildError("Nome artefatto release non valido")

    files = _collect_release_files(project_root, metadata)
    _verify_frozen_sources(project_root, metadata)
    manifest = _release_manifest(metadata, files)

    destination_dir = (output_dir or project_root / "dist").resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / artifact_name
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    package_root = Path(Path(artifact_name).stem)

    try:
        with zipfile.ZipFile(
            temporary,
            "w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for relative, content in files:
                _write_entry(archive, package_root / relative, content, relative)
            manifest_content = json.dumps(
                manifest,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ).encode("utf-8") + b"\n"
            _write_entry(
                archive,
                package_root / "RELEASE_MANIFEST.json",
                manifest_content,
                Path("RELEASE_MANIFEST.json"),
            )
        os.replace(temporary, destination)
    except (OSError, zipfile.BadZipFile) as exc:
        temporary.unlink(missing_ok=True)
        raise ReleaseBuildError("Creazione artefatto release non riuscita") from exc
    return destination


def _load_release_metadata(project_root: Path) -> dict[str, Any]:
    path = project_root / "config" / "release.json"
    try:
        metadata = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReleaseBuildError("Metadata release non leggibili") from exc
    if not isinstance(metadata, dict) or not metadata.get("artifact_name"):
        raise ReleaseBuildError("Metadata release incompleti")
    return metadata


def _collect_release_files(
    project_root: Path,
    metadata: dict[str, Any],
) -> list[tuple[Path, bytes]]:
    relative_paths = {Path(filename) for filename in ROOT_FILES}
    relative_paths.update(
        {
            Path("config/settings.json"),
            Path("config/release.json"),
        }
    )
    for source_group in ("source_of_truth", "presentation_sources"):
        for source in metadata.get(source_group, {}).values():
            relative_paths.add(Path("config/handoff") / str(source["filename"]))
    for directory in SOURCE_DIRECTORIES:
        base = project_root / directory
        if not base.is_dir():
            raise ReleaseBuildError(f"Directory release mancante: {directory}")
        relative_paths.update(
            path.relative_to(project_root)
            for path in base.rglob("*")
            if path.is_file()
        )

    files = []
    for relative in sorted(relative_paths, key=lambda path: path.as_posix()):
        if _is_excluded(relative):
            continue
        absolute = project_root / relative
        if not absolute.is_file() or absolute.is_symlink():
            raise ReleaseBuildError(f"File release non valido: {relative}")
        files.append((relative, absolute.read_bytes()))
    return files


def _is_excluded(relative: Path) -> bool:
    if relative in EXCLUDED_RELEASE_PATHS:
        return True
    if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts[:-1]):
        return True
    name = relative.name
    if name in EXCLUDED_FILE_NAMES or name.startswith(".env."):
        return True
    return relative.suffix.lower() in EXCLUDED_SUFFIXES


def _verify_frozen_sources(project_root: Path, metadata: dict[str, Any]) -> None:
    for source_group in ("source_of_truth", "presentation_sources"):
        for source in metadata.get(source_group, {}).values():
            relative = Path("config/handoff") / str(source["filename"])
            digest = hashlib.sha256((project_root / relative).read_bytes()).hexdigest()
            if digest != str(source["sha256"]):
                raise ReleaseBuildError(
                    f"Hash source-of-truth non valido: {relative.name}"
                )


def _release_manifest(
    metadata: dict[str, Any],
    files: list[tuple[Path, bytes]],
) -> dict[str, Any]:
    return {
        "release": metadata,
        "file_count": len(files) + 1,
        "files_sha256": {
            relative.as_posix(): hashlib.sha256(content).hexdigest()
            for relative, content in files
        },
    }


def _write_entry(
    archive: zipfile.ZipFile,
    archive_path: Path,
    content: bytes,
    source_path: Path,
) -> None:
    info = zipfile.ZipInfo(archive_path.as_posix(), FIXED_ZIP_TIMESTAMP)
    info.create_system = 3
    mode = 0o755 if source_path.suffix == ".sh" else 0o644
    info.external_attr = (mode & 0xFFFF) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    archive.writestr(info, content, compresslevel=9)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Genera l'artefatto pulito ResQ Prototype Architecture 1.1",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory di destinazione; default: dist/",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    project_root = Path(__file__).resolve().parents[1]
    artifact = build_release(project_root, args.output_dir)
    digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
    print(artifact)
    print(f"sha256={digest}")


if __name__ == "__main__":
    main()
