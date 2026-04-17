IMAGE ?= python:3.12
DOCKER_RUN = docker run --rm -v "$(CURDIR):/app" -w /app $(IMAGE) bash -lc
INSTALL_DEV = pip install -q httpx pytest pytest-cov pytest-asyncio pylint black isort python-dotenv

.PHONY: test lint

test:
	$(DOCKER_RUN) '$(INSTALL_DEV) && PYTHONPATH=/app python -m pytest -q tests'

lint:
	$(DOCKER_RUN) '$(INSTALL_DEV) && PYTHONPATH=/app pylint custom_components tests && isort --profile black --check-only --diff custom_components tests && black --check custom_components tests'