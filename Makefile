.PHONY: install dev-install install-agent-assets install-codex-assets install-claude-assets test

install:
	python3 -m pip install -e .

dev-install: install
	python3 scripts/install_agent_assets.py

install-agent-assets:
	python3 scripts/install_agent_assets.py

install-codex-assets:
	python3 scripts/install_agent_assets.py --codex-only

install-claude-assets:
	python3 scripts/install_agent_assets.py --claude-only

test:
	PYTHONPATH=src python3 -m pytest -q
