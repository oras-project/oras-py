.PHONY: test
test:
	/bin/bash scripts/test.sh

.PHONY: install
install:
	pip install -e .[all] --group tests

.PHONY: lint
lint:
	pre-commit run --all-files

.PHONY: testreqs
testreqs:
	pip install -e . --group tests

.PHONY: develop
develop:
	pip install -e .[all] --group tests
	pip install -r .github/dev-requirements.txt
