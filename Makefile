SHELL := /bin/bash

.PHONY: bootstrap bundle doctor repo-status check prepare-lhtb-images prepare-spp smoke-roy smoke-roy-container smoke-harbor smoke-lhtb smoke-spp run-lhtb-roy run-spp-roy run-spp-suite

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

check: smoke-roy smoke-harbor smoke-spp
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

run-lhtb-roy:
	./scripts/run-lhtb-roy.sh

run-spp-roy:
	./scripts/run-spp-roy.sh $(ARGS)

run-spp-suite:
	./scripts/run-spp-suite.sh $(ARGS)
