.PHONY: test
test:
	./scripts/test.sh

.PHONY: install
install:
	pip install -e .[all]

.PHONY: lint
lint:
	./scripts/lint.sh

.PHONY: testreqs
testreqs:
	pip install -e .[tests]

.PHONY: develop
develop:
	pip install -e .[all]
