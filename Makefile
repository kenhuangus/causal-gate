.PHONY: install dev verify-demo verify-benchmark verify-assurance verify-adapters verify-web verify-clean verify-release verify-recorded-analysis verify-live-analysis generate-recorded-analysis
UV_RUN = UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/agentflight-uv-cache} uv run --isolated
NPM = NPM_CONFIG_CACHE=$${TMPDIR:-/tmp}/agentflight-npm-cache npm
install:
	UV_CACHE_DIR=$${UV_CACHE_DIR:-/tmp/agentflight-uv-cache} uv sync --extra dev
	cd apps/web && $(NPM) ci
dev:
	$(UV_RUN) uvicorn agentflight.api:app --reload --port 8080
verify-demo:
	$(UV_RUN) --extra dev pytest
	$(UV_RUN) agentflight verify-demo
verify-benchmark:
	$(UV_RUN) agentflight benchmark
verify-assurance:
	test -n "$${AGENTFLIGHT_ATTESTATION_KEY}"
	$(UV_RUN) agentflight assurance-suite
verify-adapters:
	$(UV_RUN) --extra dev pytest tests/test_adapters.py
verify-web:
	cd apps/web && $(NPM) ci && $(NPM) test && $(NPM) run build && $(NPM) audit --audit-level=high
verify-clean:
	docker compose build
verify-release: verify-demo verify-benchmark verify-assurance verify-adapters verify-recorded-analysis verify-web
verify-recorded-analysis:
	$(UV_RUN) python scripts/verify_recorded_analysis.py
verify-live-analysis:
	$(UV_RUN) python scripts/verify_live_analysis.py
generate-recorded-analysis:
	$(UV_RUN) agentflight record-analysis --output artifacts/recorded-analysis.json
