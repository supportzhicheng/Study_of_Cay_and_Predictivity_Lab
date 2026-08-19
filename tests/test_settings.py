"""Tests for core project configuration and repository safety."""

from pathlib import Path

from src.settings import load_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_repository_relative_defaults(tmp_path: Path):
    settings = load_settings(argv=[], environ={}, project_root=tmp_path)

    assert settings.data_dir == tmp_path / "_data"
    assert settings.output_dir == tmp_path / "_output"
    assert settings.reports_dir == tmp_path / "reports"
    assert settings.p10_input_dir == tmp_path / "_data" / "input"
    assert settings.p10_reference_dir == tmp_path / "asset"
    assert settings.historical_start == "1952Q4"
    assert settings.historical_end == "1998Q3"


def test_absolute_path_override_is_preserved(tmp_path: Path):
    absolute_data = tmp_path / "external-data"

    settings = load_settings(
        argv=[],
        environ={"DATA_DIR": str(absolute_data)},
        project_root=tmp_path / "repo",
    )

    assert settings.data_dir == absolute_data


def test_cli_override_precedes_environment(tmp_path: Path):
    settings = load_settings(
        argv=["--DATA_DIR", "from-cli"],
        environ={"DATA_DIR": "from-environment"},
        project_root=tmp_path,
    )

    assert settings.data_dir == tmp_path / "from-cli"


def test_environment_precedes_dotenv(tmp_path: Path):
    (tmp_path / ".env").write_text("DATA_DIR=from-dotenv\n", encoding="utf-8")

    settings = load_settings(
        argv=[],
        environ={"DATA_DIR": "from-environment"},
        project_root=tmp_path,
    )

    assert settings.data_dir == tmp_path / "from-environment"


def test_directory_creation_is_explicit(tmp_path: Path):
    settings = load_settings(argv=[], environ={}, project_root=tmp_path)

    assert not settings.data_dir.exists()
    assert not settings.output_dir.exists()
    settings.create_directories()

    assert settings.data_dir.is_dir()
    assert settings.output_dir.is_dir()
    assert settings.reports_dir.is_dir()


def test_public_summary_redacts_credentials(tmp_path: Path):
    settings = load_settings(
        argv=[],
        environ={"WRDS_USERNAME": "researcher", "BEA_API_KEY": "secret-key"},
        project_root=tmp_path,
    )

    summary = settings.public_summary()

    assert summary["WRDS_USERNAME"] == "configured"
    assert summary["BEA_API_KEY"] == "configured"
    assert "researcher" not in summary.values()
    assert "secret-key" not in summary.values()


def test_env_example_contains_placeholders_only():
    values = {}
    for raw_line in (
        (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    ):
        line = raw_line.strip()
        if line and not line.startswith("#"):
            key, value = line.split("=", 1)
            values[key] = value

    assert values["WRDS_USERNAME"] == ""
    assert values["BEA_API_KEY"] == ""


def test_generated_and_private_paths_are_ignored():
    ignore_rules = (
        (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    )

    for required_rule in (".env", "asset/", "_data/", "_output/", "reports/build/"):
        assert required_rule in ignore_rules


def test_core_package_has_no_simulated_data_generator():
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT_ROOT / "src").rglob("*.py")
    )

    assert "make_synthetic_dataset" not in source
