.PHONY: test
test: develop
	./scripts/test.sh

.PHONY: lint
lint: testreqs
	./scripts/lint.sh

.PHONY: testreqs
testreqs:
	pip install -e .[tests]

.PHONY: develop
develop:
	pip install -e .[all]
