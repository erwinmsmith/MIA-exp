SHELL := /bin/bash

.PHONY: bootstrap bundle doctor repo-status check prepare-lhtb-images prepare-spp prepare-evoagent smoke-roy smoke-roy-container smoke-harbor smoke-lhtb smoke-spp smoke-evoagent run-lhtb-roy run-spp-roy run-spp-suite run-evoagent-suite

bootstrap:
	./scripts/bootstrap.sh

bundle:
	./scripts/build-roy-bundle.sh

doctor:
	./scripts/doctor.sh

repo-status:
	./scripts/repo-status.sh

prepare-lhtb-images:
	./scripts/prepare-lhtb-images.sh

prepare-spp:
	./scripts/prepare-spp.sh

prepare-evoagent:
	./scripts/prepare-evoagent.sh

check: smoke-roy smoke-harbor smoke-spp smoke-evoagent
	./scripts/repo-status.sh --require-clean-submodules

smoke-roy:
	./scripts/smoke-roy.sh

smoke-roy-container:
	./scripts/smoke-roy-container.sh

smoke-harbor:
	./scripts/smoke-harbor.sh

smoke-lhtb:
	./scripts/smoke-lhtb.sh

smoke-spp:
	./scripts/smoke-spp.sh

smoke-evoagent:
	PYTHONPATH=src .venv/bin/python -m unittest tests.test_evoagent_runner

run-lhtb-roy:
	./scripts/run-lhtb-roy.sh

run-spp-roy:
	./scripts/run-spp-roy.sh $(ARGS)

run-spp-suite:
	./scripts/run-spp-suite.sh $(ARGS)

run-evoagent-suite:
	./scripts/run-evoagent-suite.sh $(ARGS)
