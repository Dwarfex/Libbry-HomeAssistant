IMAGE ?= python:3.14
DOCKER_RUN = docker run --rm -v "$(CURDIR):/app" -w /app $(IMAGE) bash -lc
INSTALL_BASE = pip install -q httpx pytest pytest-cov pytest-asyncio pylint black isort python-dotenv
INSTALL_TEST = $(INSTALL_BASE) homeassistant

.PHONY: test lint test-hamburg-live

test: lint
	$(DOCKER_RUN) '$(INSTALL_TEST) && PYTHONPATH=/app python -m pytest -q tests'

lint:
	$(DOCKER_RUN) '$(INSTALL_BASE) && isort --profile black custom_components tests && black custom_components tests && PYTHONPATH=/app pylint custom_components tests'

test-hamburg-live:
	@set -e; \
	H_USER="$${HAMBURG_USER_ID:-}"; \
	H_PIN="$${HAMBURG_PIN:-}"; \
	if [ -z "$$H_USER" ]; then read -r -p "Hamburg Benutzerkennung: " H_USER; fi; \
	if [ -z "$$H_PIN" ]; then read -r -s -p "Hamburg PIN: " H_PIN; echo ""; fi; \
	docker run --rm -i -v "$(CURDIR):/app" -w /app -e HAMBURG_USER_ID="$$H_USER" -e HAMBURG_PIN="$$H_PIN" $(IMAGE) bash -lc '$(INSTALL_TEST) && PYTHONPATH=/app python /app/tests/hamburg_live_check.py'