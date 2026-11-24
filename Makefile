.PHONY: install test lint demo api audit
install:
	python -m pip install -e '.[api,ml,streaming,dashboard,vision,images,dev]'
test:
	node --test tests/test_extension_auto.cjs
	python -m pytest -m 'not spark and not kafka and not vision and not browser'
lint:
	python -m ruff check src tests scripts
	python -m compileall -q src
	node --check extension/background.js
	node --check extension/popup.js
	node --check extension/page-warning.js
	node --check extension/scan-core.js
demo:
	bash scripts/demo.sh
api:
	uvicorn phishguard.api.main:create_app --factory --host 127.0.0.1 --port 8000 --no-access-log
audit:
	python -m pip_audit
	python -m bandit -r src -ll

.PHONY: test-vision test-spark test-browser package
test-vision:
	python -m pytest -m vision -v
test-spark:
	python -m pytest -m spark -v
test-browser:
	PHISHGUARD_TEST_BROWSER=true python -m pytest -m browser -v
package:
	python scripts/package_release.py --output ../PhishGuard-2.0-source.zip

.PHONY: launch doctor
launch:
	bash start_local.sh
doctor:
	python scripts/doctor.py --model models/trained/url-model.json $(if $(wildcard models/trained/vision-model.pt),--vision-model models/trained/vision-model.pt)
