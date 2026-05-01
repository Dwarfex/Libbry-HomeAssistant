IMAGE ?= python:3.14
DOCKER_RUN = docker run --rm -v "$(CURDIR):/app" -w /app $(IMAGE) bash -lc
INSTALL_DEV = pip install -q httpx pytest pytest-cov pytest-asyncio pylint black isort python-dotenv

.PHONY: test lint

test: lint
	$(DOCKER_RUN) '$(INSTALL_DEV) && PYTHONPATH=/app python -m pytest -q tests'

lint:
	$(DOCKER_RUN) '$(INSTALL_DEV) && isort --profile black custom_components tests && black custom_components tests && PYTHONPATH=/app pylint custom_components tests'