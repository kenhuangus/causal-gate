from pathlib import Path
import subprocess

import yaml


ROOT = Path(__file__).parents[1]
SHELL_SCRIPTS = sorted((ROOT / "scripts").glob("**/*.sh"))


def test_all_shell_deployment_scripts_parse():
    assert SHELL_SCRIPTS
    for script in SHELL_SCRIPTS:
        source = script.read_text().replace("\r\n", "\n").encode()
        subprocess.run(["bash", "-n"], input=source, check=True)


def test_local_launchers_enable_explicit_byok_without_storing_an_openai_key():
    launchers = [
        ROOT / "scripts/local/run-macos-linux.sh",
        ROOT / "scripts/local/run-windows.ps1",
    ]
    for launcher in launchers:
        source = launcher.read_text()
        assert "CAUSALGATE_LIVE_ANALYSIS_ENABLED=true" in source
        assert "OPENAI_API_KEY" not in source
        assert ".causalgate.local.env" in source


def test_cloud_scripts_use_managed_causalgate_secrets_but_never_deploy_openai_key():
    gcp = (ROOT / "scripts/deploy/deploy-gcp-cloud-run.sh").read_text()
    aws = (ROOT / "scripts/deploy/deploy-aws-apprunner.sh").read_text()
    for source in (gcp, aws):
        assert "OPENAI_API_KEY" not in source
        assert "CAUSALGATE_LIVE_ANALYSIS_ENABLED" in source
        assert "CAUSALGATE_ATTESTATION_KEY" in source
        assert "CAUSALGATE_GRANT_SIGNING_KEY" in source
    assert "gcloud secrets" in gcp
    assert "aws secretsmanager" in aws


def test_compose_defaults_to_no_key_byok_mode_and_configurable_host_port():
    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    service = compose["services"]["causalgate"]
    assert service["ports"] == ["${CAUSALGATE_PORT:-8080}:8080"]
    assert service["environment"]["CAUSALGATE_LIVE_ANALYSIS_ENABLED"] == "${CAUSALGATE_LIVE_ANALYSIS_ENABLED:-true}"
    assert service["environment"]["OPENAI_API_KEY"] == "${OPENAI_API_KEY:-}"


def test_deployment_documentation_covers_every_supported_target():
    documentation = (ROOT / "docs/DEPLOYMENT.md").read_text()
    for heading in ("### Windows", "### macOS", "### Linux", "## Google Cloud Run", "## AWS App Runner"):
        assert heading in documentation
    assert "never create, request, or deploy an OpenAI API key" in documentation
