import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _tracked_text() -> dict[str, str]:
    paths = subprocess.run(
        ["git", "ls-files", "-co", "--exclude-standard"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    text = {}
    for relative in paths:
        if relative.startswith(("docs/design/", "docs/benchmarks/", "scripts/benchmarks/")):
            continue
        if relative == "scripts/dogfood_mcp_flow.py":
            continue
        path = ROOT / relative
        if path.is_file():
            try:
                text[relative] = path.read_text()
            except UnicodeDecodeError:
                pass
    return text


def test_public_tree_has_no_private_checkout_coupling():
    forbidden = ("/home/", "~/peace", "$HOME/peace", "PEACE_SOURCE_ROOT", "docs/design/")
    violations = []
    for relative, content in _tracked_text().items():
        if relative == "tests/test_repository_self_containment.py":
            continue
        for marker in forbidden:
            if marker in content:
                violations.append(f"{relative}: {marker}")

    assert violations == []


def test_old_identity_only_appears_in_explicit_provenance():
    markers = ("peace-tool-pool", "peace_tool_pool", "peace-tool-pool-mcp")
    violations = []
    for relative, content in _tracked_text().items():
        if relative in {
            "docs/provenance.md",
            "tests/test_release_identity.py",
            "tests/test_repository_self_containment.py",
        }:
            continue
        for marker in markers:
            if marker in content:
                violations.append(f"{relative}: {marker}")

    assert violations == []


def test_direnv_is_opt_in_and_side_effect_free():
    assert not (ROOT / ".envrc").exists()
    example = (ROOT / ".envrc.example").read_text()
    assert "uv sync" not in example


def test_project_opencode_config_is_portable():
    config = (ROOT / "opencode.json").read_text()
    assert str(ROOT) not in config
    assert '"enabled": false' not in config
