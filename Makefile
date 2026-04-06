.PHONY: test test-queries test-routes test-templates test-schema install-test-deps

# Run the full test suite
# Requires Dolt running on 127.0.0.1:3306 (or override DOLT_HOST/DOLT_PORT)
test:
	python3 -m pytest tests/ -v

# Run only query tests (catches SQL column mismatches)
test-queries:
	python3 -m pytest tests/test_queries.py -v

# Run only route tests (catches HTTP 500s from queries or templates)
test-routes:
	python3 -m pytest tests/test_routes.py -v

# Run only template rendering tests (no DB needed — catches Jinja2 column mismatches)
test-templates:
	python3 -m pytest tests/test_templates.py -v

# Run only schema validation tests (compares query column refs against DB schema)
test-schema:
	python3 -m pytest tests/test_schema.py -v

# Install test dependencies
install-test-deps:
	pip3 install -e ".[test]"
