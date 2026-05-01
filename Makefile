IMAGE ?= python:3.14
DOCKER_RUN = docker run --rm -v "$(CURDIR):/app" -w /app $(IMAGE) bash -lc
INSTALL_BASE = pip install -q httpx pytest pytest-cov pytest-asyncio pylint black isort python-dotenv
INSTALL_TEST = $(INSTALL_BASE) homeassistant

.PHONY: test lint

test: lint
	$(DOCKER_RUN) '$(INSTALL_TEST) && PYTHONPATH=/app python -m pytest -q tests'

lint:
	$(DOCKER_RUN) '$(INSTALL_BASE) && isort --profile black custom_components tests && black custom_components tests && PYTHONPATH=/app pylint custom_components tests'