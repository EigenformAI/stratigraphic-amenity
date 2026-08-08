"""Install attributed PEACE runtime, model, and knowledge assets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
from importlib.resources import files
import os
from pathlib import Path, PurePosixPath
import shutil
import stat
import sys
import tempfile
import tomllib
from typing import Any, Callable, Iterable, Mapping, Sequence
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from .paths import configured_data_root


class AssetInstallError(RuntimeError):
    """An optional asset could not be safely installed."""


@dataclass(frozen=True)
class InstallResult:
    asset_id: str
    status: str
    destination: Path


DownloadFile = Callable[[dict[str, Any], Path], None]


def load_manifest() -> dict[str, Any]:
    resource = files("stratigraphic_amenity").joinpath("data/manifest.toml")
    if resource.is_file():
        content = resource.read_text(encoding="utf-8")
    else:
        content = (Path(__file__).resolve().parents[2] / "assets" / "manifest.toml").read_text(
            encoding="utf-8"
        )
    return tomllib.loads(content)


def install_asset(
    asset: dict[str, Any],
    *,
    root: str | Path,
    force: bool = False,
    download_file: DownloadFile | None = None,
) -> InstallResult:
    policy = str(asset.get("redistribution"))
    if policy not in {"download-only", "source-sync"}:
        raise AssetInstallError(f"Asset policy {policy!r} is not installable.")
    relative_destination = _safe_relative(str(asset["destination"]), label="destination")
    install_root = Path(root).expanduser().resolve()
    destination = (install_root / relative_destination).resolve()
    if not destination.is_relative_to(install_root):
        raise AssetInstallError(f"Asset destination is outside the install root: {destination.name}")
    checks = [_safe_relative(str(value), label="post-install path") for value in asset["post_install"]]
    if destination.exists() and all((destination / check).is_file() for check in checks):
        if not force:
            return InstallResult(str(asset["id"]), "already-installed", destination)
    elif destination.exists() and not force:
        raise AssetInstallError(
            f"Asset destination is incomplete: {relative_destination}. Re-run with --force."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f".{asset['id']}.", dir=destination.parent) as temp:
        temp_root = Path(temp)
        archive_path = temp_root / "download.zip"
        (download_file or _download_file)(asset, archive_path)
        _verify_download_size(asset, archive_path)
        _verify_checksum(asset, archive_path)
        staged = temp_root / "content"
        staged.mkdir()
        _extract_selected(asset, archive_path, staged)
        _apply_patches(asset, staged)
        _verify_tree_checksum(asset, staged)
        missing = [str(check) for check in checks if not (staged / check).is_file()]
        if missing:
            raise AssetInstallError(
                f"Asset archive is missing expected files: {', '.join(missing)}"
            )
        _replace_directory(staged, destination, force=force)
    return InstallResult(str(asset["id"]), "installed", destination)


def provision_assets(
    asset_ids: Iterable[str],
    *,
    root: str | Path,
    force: bool = False,
    manifest: Mapping[str, Any] | None = None,
    download_file: DownloadFile | None = None,
) -> list[InstallResult]:
    """Install an ordered set of approved manifest assets."""

    requested = tuple(dict.fromkeys(str(asset_id) for asset_id in asset_ids))
    if not requested:
        raise AssetInstallError("At least one asset ID is required.")
    assets = list((manifest or load_manifest()).get("asset", []))
    by_id: dict[str, dict[str, Any]] = {}
    for asset in assets:
        asset_id = str(asset["id"])
        if asset_id in by_id:
            raise AssetInstallError(f"Duplicate asset ID in manifest: {asset_id}")
        by_id[asset_id] = asset
    unknown = [asset_id for asset_id in requested if asset_id not in by_id]
    if unknown:
        raise AssetInstallError(f"Unknown asset ID: {unknown[0]}")
    return [
        install_asset(by_id[asset_id], root=root, force=force, download_file=download_file)
        for asset_id in requested
    ]


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_id", nargs="?")
    parser.add_argument("--all", action="store_true", help="Install every approved asset.")
    parser.add_argument("--list", action="store_true", help="List sources without downloading.")
    parser.add_argument("--root", type=Path)
    parser.add_argument("--force", action="store_true", help="Atomically replace an installation.")
    args = parser.parse_args(argv)
    root = configured_data_root(args.root)
    assets = load_manifest()["asset"]

    if args.list:
        for asset in assets:
            size = asset.get("size_bytes", "source")
            print(
                f"{asset['id']}\t{asset['version']}\t{asset['redistribution']}\t"
                f"{asset['license']}\t{size}\t{asset['destination']}"
            )
        return 0

    if args.all == bool(args.asset_id):
        parser.error("choose exactly one asset ID or --all")
    selected_ids = [str(asset["id"]) for asset in assets] if args.all else [str(args.asset_id)]
    try:
        for result in provision_assets(selected_ids, root=root, force=args.force, manifest={"asset": assets}):
            print(f"{result.asset_id}: {result.status} at {result.destination}")
    except AssetInstallError as exc:
        print(str(exc), file=sys.stderr)
        return 2 if str(exc).startswith("Unknown asset ID:") else 3
    return 0


def _download_file(asset: dict[str, Any], destination: Path) -> None:
    url = str(asset["urls"][0])
    if asset.get("download") == "gdown":
        try:
            import gdown  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:
            raise AssetInstallError(
                "Google Drive downloads require the 'assets' extra: "
                "pip install 'stratigraphic-amenity[assets]'."
            ) from exc
        try:
            result = gdown.download(url=url, output=str(destination), quiet=False, fuzzy=True)
        except Exception as exc:
            raise AssetInstallError(f"Download failed for asset {asset['id']}: {exc}") from exc
        if not result:
            raise AssetInstallError(f"Download failed for asset {asset['id']}.")
        return

    request = Request(url, headers={"User-Agent": "stratigraphic-amenity/0.1.0"})
    maximum = int(asset.get("size_bytes") or 1024 * 1024 * 1024)
    downloaded = 0
    try:
        with urlopen(request, timeout=60) as response, destination.open("wb") as output:
            while chunk := response.read(1024 * 1024):
                downloaded += len(chunk)
                if downloaded > maximum:
                    raise AssetInstallError(f"Download exceeded the size limit for {asset['id']}.")
                output.write(chunk)
    except OSError as exc:
        raise AssetInstallError(f"Download failed for asset {asset['id']}: {exc}") from exc


def _verify_checksum(asset: dict[str, Any], archive_path: Path) -> None:
    expected = str(asset.get("sha256") or "").lower()
    if not expected:
        return
    digest = hashlib.sha256()
    with archive_path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise AssetInstallError(f"Downloaded checksum does not match asset {asset['id']}.")


def _verify_download_size(asset: dict[str, Any], path: Path) -> None:
    maximum = int(asset.get("size_bytes") or 1024 * 1024 * 1024)
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise AssetInstallError(f"Download failed for asset {asset['id']}.") from exc
    if size > maximum:
        raise AssetInstallError(f"Download exceeded the size limit for {asset['id']}.")


def _verify_tree_checksum(asset: dict[str, Any], root: Path) -> None:
    expected = str(asset.get("tree_sha256") or "").lower()
    if not expected:
        return
    digest = hashlib.sha256()
    for path in sorted(candidate for candidate in root.rglob("*") if candidate.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        with path.open("rb") as source:
            while chunk := source.read(1024 * 1024):
                digest.update(chunk)
        digest.update(b"\0")
    if digest.hexdigest() != expected:
        raise AssetInstallError(f"Extracted tree checksum does not match asset {asset['id']}.")


def _extract_selected(asset: dict[str, Any], archive_path: Path, destination: Path) -> None:
    prefix = PurePosixPath(str(asset["archive_subdir"])).parts
    maximum = int(asset.get("max_extracted_bytes") or 2 * 1024 * 1024 * 1024)
    extracted_files = 0
    extracted_bytes = 0
    try:
        with ZipFile(archive_path) as archive:
            for member in archive.infolist():
                name = member.filename
                path = PurePosixPath(name)
                if path.is_absolute() or ".." in path.parts or "\\" in name:
                    raise AssetInstallError(f"Refusing unsafe archive member: {name}")
                mode = member.external_attr >> 16
                if stat.S_ISLNK(mode):
                    raise AssetInstallError(f"Refusing archive symlink: {name}")
                relative = _relative_after(path.parts, prefix)
                if relative is None or not relative or member.is_dir():
                    continue
                if member.file_size > maximum - extracted_bytes:
                    raise AssetInstallError(f"Archive exceeded the extracted size limit for {asset['id']}.")
                target = destination.joinpath(*relative)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        extracted_bytes += len(chunk)
                        if extracted_bytes > maximum:
                            raise AssetInstallError(
                                f"Archive exceeded the extracted size limit for {asset['id']}."
                            )
                        output.write(chunk)
                extracted_files += 1
    except BadZipFile as exc:
        raise AssetInstallError(f"Downloaded asset is not a valid ZIP: {asset['id']}.") from exc
    if extracted_files == 0:
        raise AssetInstallError(f"Archive subtree was not found for asset {asset['id']}.")


def _relative_after(parts: tuple[str, ...], prefix: tuple[str, ...]) -> tuple[str, ...] | None:
    for index in range(len(parts) - len(prefix) + 1):
        if parts[index : index + len(prefix)] == prefix:
            return parts[index + len(prefix) :]
    return None


def _apply_patches(asset: dict[str, Any], destination: Path) -> None:
    for patch in asset.get("patches", []):
        if patch != "remove-parent-sys-path-hook":
            raise AssetInstallError(f"Unknown asset patch: {patch}")
        init_path = destination / "__init__.py"
        content = init_path.read_text(encoding="utf-8")
        hook = 'import os\nos.sys.path.append(f"{os.path.dirname(os.path.realpath(__file__))}/..")\n'
        if hook not in content:
            raise AssetInstallError("Expected PEACE Ultralytics path hook was not found.")
        init_path.write_text(content.replace(hook, ""), encoding="utf-8")


def _replace_directory(staged: Path, destination: Path, *, force: bool) -> None:
    backup = destination.with_name(f".{destination.name}.backup-{os.getpid()}")
    if destination.exists():
        if not force:
            raise AssetInstallError(f"Asset destination already exists: {destination.name}")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(destination, backup)
    try:
        os.replace(staged, destination)
    except Exception:
        if backup.exists() and not destination.exists():
            os.replace(backup, destination)
        raise
    if backup.exists():
        shutil.rmtree(backup)


def _safe_relative(value: str, *, label: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts or not path.parts:
        raise AssetInstallError(f"Unsafe {label}: {value}")
    return path


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "AssetInstallError",
    "InstallResult",
    "install_asset",
    "load_manifest",
    "main",
    "provision_assets",
]
