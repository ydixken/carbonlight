.PHONY: install uninstall lint test test-unit test-smoke clean help

help:
	@echo "carbonlight — make targets:"
	@echo "  install      Install daemon, config, and systemd unit (sudo)"
	@echo "  uninstall    Remove binary and service unit (sudo)"
	@echo "  lint         Run ruff and py_compile"
	@echo "  test         Run unit tests (no hardware)"
	@echo "  test-smoke   Run end-to-end uinput test (sudo, hardware required)"
	@echo "  clean        Remove caches and build artifacts"

install:
	sudo bash install.sh

uninstall:
	sudo bash uninstall.sh

lint:
	ruff check .
	/usr/bin/python3 -m py_compile carbonlight.py

test: test-unit
	@echo "For end-to-end: 'sudo make test-smoke'"

test-unit:
	/usr/bin/python3 -m pytest tests/test_unit.py -v

test-smoke:
	sudo /usr/bin/python3 -m pytest tests/test_smoke.py -v

clean:
	rm -rf __pycache__ tests/__pycache__ .pytest_cache .ruff_cache *.egg-info build dist
