from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tomllib
from types import SimpleNamespace
from zipfile import ZipFile, ZipInfo

import pytest

import stratigraphic_amenity.asset_installer as asset_installer
from stratigraphic_amenity.asset_installer import AssetInstallError, install_asset, provision_assets


ROOT = Path(__file__).resolve().parents[1]


def test_manifest_approves_upstream_runtime_weights_and_knowledge():
    manifest = tomllib.loads((ROOT / "assets/manifest.toml").read_text())
    assets = {asset["id"]: asset for asset in manifest["asset"]}

    assert set(assets) == {
        "peace-yolov10-runtime",
        "peace-layout-detectors",
        "peace-knowledge-base",
    }
    assert assets["peace-yolov10-runtime"]["redistribution"] == "source-sync"
    assert assets["peace-yolov10-runtime"]["license"] == "AGPL-3.0-only"
    assert assets["peace-layout-detectors"]["redistribution"] == "download-only"
    assert assets["peace-layout-detectors"]["license"] == "MIT"
    assert assets["peace-layout-detectors"]["sha256"] == (
        "10701bba7a94f54cbd79cae79ca0a79eba54b82d7e8552e5a78ed5b2dcbb09da"
    )
    assert assets["peace-knowledge-base"]["redistribution"] == "source-sync"
    assert "CC0-1.0" in assets["peace-knowledge-base"]["license"]
    assert "CC-BY-SA-4.0" in assets["peace-knowledge-base"]["license"]
    assert assets["peace-knowledge-base"]["license_components"] == [
        "K2 material: MIT",
        "USGS earthquake history: CC0-1.0 / United States government public domain",
        "GEM Global Active Faults: CC-BY-SA-4.0",
    ]
    for asset in assets.values():
        assert asset["urls"]
        assert asset["source"]
        assert asset["destination"]
        assert asset["required_for"]
        assert asset["attribution"]
        assert asset["max_extracted_bytes"] > 0
        assert len(asset.get("sha256") or asset.get("tree_sha256")) == 64


def test_notice_names_all_incorporated_material():
    notice = (ROOT / "NOTICE").read_text(encoding="utf-8")

    assert "Ultralytics" in notice and "AGPL-3.0" in notice
    assert "USGS" in notice and "CC0" in notice
    assert "GEM" in notice and "CC BY-SA 4.0" in notice
    assert "Microsoft PEACE" in notice and "MIT" in notice


def test_asset_installer_lists_approved_sources_without_downloading():
    result = subprocess.run(
        [sys.executable, "-m", "stratigraphic_amenity.asset_installer", "--list"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "peace-layout-detectors" in result.stdout
    assert "download-only" in result.stdout
    assert "source-sync" in result.stdout
    assert "excluded" not in result.stdout


def test_source_sync_extracts_only_selected_subtree_and_is_idempotent(tmp_path):
    archive = tmp_path / "source.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("PEACE-revision/dependencies/knowledge/k2_rock_type.json", "{}")
        bundle.writestr("PEACE-revision/private.txt", "must not install")
    asset = _fixture_asset(
        archive,
        redistribution="source-sync",
        archive_subdir="dependencies/knowledge",
        destination="assets/knowledge",
        post_install=["k2_rock_type.json"],
    )
    calls = {"count": 0}

    def downloader(_asset, destination):
        calls["count"] += 1
        shutil.copyfile(archive, destination)

    first = install_asset(asset, root=tmp_path / "install", download_file=downloader)
    second = install_asset(asset, root=tmp_path / "install", download_file=downloader)

    assert first.status == "installed"
    assert second.status == "already-installed"
    assert calls["count"] == 1
    assert (tmp_path / "install/assets/knowledge/k2_rock_type.json").read_text() == "{}"
    assert not (tmp_path / "install/private.txt").exists()


def test_download_only_verifies_archive_checksum(tmp_path):
    archive = tmp_path / "models.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("models/det_component/weights/best.pt", "component")
    asset = _fixture_asset(
        archive,
        redistribution="download-only",
        archive_subdir="models",
        destination="assets/models",
        post_install=["det_component/weights/best.pt"],
        sha256="0" * 64,
    )

    with pytest.raises(AssetInstallError, match="checksum"):
        install_asset(
            asset,
            root=tmp_path / "install",
            download_file=lambda _asset, destination: shutil.copyfile(archive, destination),
        )

    assert not (tmp_path / "install/assets/models").exists()


def test_installer_rejects_archive_traversal(tmp_path):
    archive = tmp_path / "unsafe.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("PEACE-revision/dependencies/knowledge/../../escape.txt", "escape")
        bundle.writestr("PEACE-revision/dependencies/knowledge/k2_rock_type.json", "{}")
    asset = _fixture_asset(
        archive,
        redistribution="source-sync",
        archive_subdir="dependencies/knowledge",
        destination="assets/knowledge",
        post_install=["k2_rock_type.json"],
    )

    with pytest.raises(AssetInstallError, match="unsafe archive member"):
        install_asset(
            asset,
            root=tmp_path / "install",
            download_file=lambda _asset, destination: shutil.copyfile(archive, destination),
        )

    assert not (tmp_path / "escape.txt").exists()


def test_installer_rejects_symlinks_and_extraction_overflow(tmp_path):
    symlink_archive = tmp_path / "symlink.zip"
    link = ZipInfo("PEACE-revision/dependencies/knowledge/k2_rock_type.json")
    link.create_system = 3
    link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(symlink_archive, "w") as bundle:
        bundle.writestr(link, "../../outside")
    symlink_asset = _fixture_asset(
        symlink_archive,
        redistribution="source-sync",
        archive_subdir="dependencies/knowledge",
        destination="assets/knowledge",
        post_install=["k2_rock_type.json"],
    )

    with pytest.raises(AssetInstallError, match="archive symlink"):
        install_asset(
            symlink_asset,
            root=tmp_path / "symlink-install",
            download_file=lambda _asset, destination: shutil.copyfile(symlink_archive, destination),
        )

    large_archive = tmp_path / "large.zip"
    with ZipFile(large_archive, "w") as bundle:
        bundle.writestr("PEACE-revision/dependencies/knowledge/k2_rock_type.json", "overflow")
    large_asset = _fixture_asset(
        large_archive,
        redistribution="source-sync",
        archive_subdir="dependencies/knowledge",
        destination="assets/knowledge",
        post_install=["k2_rock_type.json"],
        max_extracted_bytes=4,
    )

    with pytest.raises(AssetInstallError, match="extracted size limit"):
        install_asset(
            large_asset,
            root=tmp_path / "large-install",
            download_file=lambda _asset, destination: shutil.copyfile(large_archive, destination),
        )


def test_installer_rejects_destination_symlink_escape(tmp_path):
    archive = tmp_path / "source.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("PEACE-revision/dependencies/knowledge/k2_rock_type.json", "{}")
    asset = _fixture_asset(
        archive,
        redistribution="source-sync",
        archive_subdir="dependencies/knowledge",
        destination="assets/knowledge",
        post_install=["k2_rock_type.json"],
    )
    root = tmp_path / "install"
    outside = tmp_path / "outside"
    root.mkdir()
    outside.mkdir()
    (root / "assets").symlink_to(outside, target_is_directory=True)

    with pytest.raises(AssetInstallError, match="outside the install root"):
        install_asset(
            asset,
            root=root,
            download_file=lambda _asset, destination: shutil.copyfile(archive, destination),
        )


def test_installer_verifies_tree_checksum_and_force_replaces_incomplete_destination(tmp_path):
    archive = tmp_path / "source.zip"
    with ZipFile(archive, "w") as bundle:
        bundle.writestr("PEACE-revision/dependencies/knowledge/k2_rock_type.json", "{}")
    asset = _fixture_asset(
        archive,
        redistribution="source-sync",
        archive_subdir="dependencies/knowledge",
        destination="assets/knowledge",
        post_install=["k2_rock_type.json"],
        tree_sha256="0" * 64,
    )
    def downloader(_asset, destination):
        shutil.copyfile(archive, destination)

    with pytest.raises(AssetInstallError, match="tree checksum"):
        install_asset(asset, root=tmp_path / "checksum-install", download_file=downloader)

    asset.pop("tree_sha256")
    destination = tmp_path / "force-install/assets/knowledge"
    destination.mkdir(parents=True)
    (destination / "stale.txt").write_text("stale")
    with pytest.raises(AssetInstallError, match="incomplete"):
        install_asset(asset, root=tmp_path / "force-install", download_file=downloader)

    result = install_asset(
        asset,
        root=tmp_path / "force-install",
        force=True,
        download_file=downloader,
    )
    assert result.status == "installed"
    assert not (destination / "stale.txt").exists()


def test_gdown_failure_and_oversize_are_reported_as_asset_errors(tmp_path, monkeypatch):
    asset = _fixture_asset(
        tmp_path / "unused.zip",
        redistribution="download-only",
        archive_subdir="models",
        destination="assets/models",
        post_install=["det_component/weights/best.pt"],
        size_bytes=4,
    )
    asset["download"] = "gdown"

    def fail_download(**_kwargs):
        raise RuntimeError("network detail")

    monkeypatch.setitem(sys.modules, "gdown", SimpleNamespace(download=fail_download))
    with pytest.raises(AssetInstallError, match="Download failed"):
        install_asset(asset, root=tmp_path / "failed")

    def oversized_download(*, output, **_kwargs):
        Path(output).write_bytes(b"12345")
        return output

    monkeypatch.setitem(sys.modules, "gdown", SimpleNamespace(download=oversized_download))
    with pytest.raises(AssetInstallError, match="size limit"):
        install_asset(asset, root=tmp_path / "oversized")


def test_provision_assets_validates_all_ids_before_download(tmp_path):
    calls = []
    manifest = {
        "asset": [
            {
                "id": "known",
                "redistribution": "download-only",
                "destination": "assets/known",
                "post_install": ["file"],
            }
        ]
    }

    with pytest.raises(AssetInstallError, match="Unknown asset ID"):
        provision_assets(
            ["known", "unknown"],
            root=tmp_path,
            manifest=manifest,
            download_file=lambda *_args: calls.append(True),
        )

    assert calls == []


def test_force_replacement_restores_previous_destination_on_failure(tmp_path, monkeypatch):
    destination = tmp_path / "assets"
    staged = tmp_path / "staged"
    destination.mkdir()
    staged.mkdir()
    (destination / "value.txt").write_text("previous")
    (staged / "value.txt").write_text("replacement")
    real_replace = asset_installer.os.replace

    def fail_staged_replace(source, target):
        if Path(source) == staged and Path(target) == destination:
            raise OSError("simulated replacement failure")
        real_replace(source, target)

    monkeypatch.setattr(asset_installer.os, "replace", fail_staged_replace)

    with pytest.raises(OSError, match="simulated replacement failure"):
        asset_installer._replace_directory(staged, destination, force=True)

    assert (destination / "value.txt").read_text() == "previous"


def _fixture_asset(
    archive: Path,
    *,
    redistribution: str,
    archive_subdir: str,
    destination: str,
    post_install: list[str],
    sha256: str = "",
    tree_sha256: str = "",
    max_extracted_bytes: int = 1024,
    size_bytes: int | None = None,
):
    asset = {
        "id": "fixture",
        "version": "1",
        "kind": "fixture",
        "urls": [archive.as_uri()],
        "sha256": sha256,
        "tree_sha256": tree_sha256,
        "max_extracted_bytes": max_extracted_bytes,
        "destination": destination,
        "license": "MIT",
        "source": archive.as_uri(),
        "redistribution": redistribution,
        "required_for": ["test"],
        "attribution": "fixture",
        "archive_subdir": archive_subdir,
        "post_install": post_install,
    }
    if size_bytes is not None:
        asset["size_bytes"] = size_bytes
    return asset
