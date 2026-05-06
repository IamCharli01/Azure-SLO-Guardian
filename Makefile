# Makefile for Azure SLO Guardian

.PHONY: help install install-dev test lint format type-check clean build

help:
	@echo "Azure SLO Guardian - Development Commands"
	@echo ""
	@echo "make install       - Install package"
	@echo "make install-dev   - Install package with development dependencies"
	@echo "make test          - Run tests"
	@echo "make lint          - Run linters"
	@echo "make format        - Format code with black"
	@echo "make type-check    - Run type checking with mypy"
	@echo "make clean         - Remove build artifacts"
	@echo "make build         - Build package"

install:
	pip install -e .

install-dev:
	pip install -e ".[dev]"

test:
	pytest -v

test-cov:
	pytest --cov=azure_slo_guardian --cov-report=html --cov-report=term

lint:
	ruff check azure_slo_guardian tests
	black --check azure_slo_guardian tests

format:
	black azure_slo_guardian tests
	ruff check --fix azure_slo_guardian tests

type-check:
	mypy azure_slo_guardian

clean:
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info
	rm -rf .pytest_cache
	rm -rf .mypy_cache
	rm -rf .ruff_cache
	rm -rf htmlcov
	rm -rf .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

build:
	python -m build

publish-test:
	python -m twine upload --repository testpypi dist/*

publish:
	python -m twine upload dist/*
