PY ?= python3
NODE ?= node

.PHONY: test compile art clean

test: compile
	$(PY) tests/test_policy.py
	$(PY) tests/test_bus_api.py

compile:
	$(PY) -m py_compile bus/server.py node/wr_node.py cli/armada.py \
		tests/test_policy.py tests/test_bus_api.py

art:
	$(NODE) art/build.mjs
	$(NODE) art/build.mjs --light

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
