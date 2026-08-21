PYTHON ?= python3

.PHONY: fixture portfolio-fixture research-fixture test compile repository-check validate serve clean-derived

fixture: portfolio-fixture research-fixture

portfolio-fixture:
	$(PYTHON) -m src.portfolio.cli build-fixture --dashboard-output data/derived/portfolio/fixture-data.js

research-fixture:
	$(PYTHON) -m src.rebuild.cli build-fixture

test:
	$(PYTHON) -m pytest -q

compile:
	$(PYTHON) -m compileall -q src tests app.py

repository-check:
	$(PYTHON) -m src.rebuild.validation

validate: compile test repository-check fixture

serve:
	$(PYTHON) app.py

clean-derived:
	rm -rf data/derived/portfolio data/derived/rebuild
