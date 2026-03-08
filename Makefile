.PHONY: extract format lint test all

extract:
	python scripts/extract.py

format:
	black src/ api/

lint:
	ruff check src/ api/

test:
	pytest tests/ -v

all: extract format lint test
