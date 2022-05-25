.PHONY: test
test:
	/bin/bash scripts/test.sh

.PHONY: install
install:
	pip install -e .[all]

.PHONY: lint
lint:
	/bin/bash scripts/lint.sh

.PHONY: testreqs
testreqs:
	pip install -e .[tests]

.PHONY: develop
develop:
	pip install -e .[all]
