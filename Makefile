.PHONY: test
test: develop
	./scripts/test.sh

.PHONY: lint
lint:
	./scripts/lint.sh

.PHONY: develop
develop:
	pip install -e .
