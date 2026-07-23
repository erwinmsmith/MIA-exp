SHELL := /bin/bash

.PHONY: bootstrap bundle doctor repo-status check prepare-lhtb-images smoke-roy smoke-roy-container smoke-harbor smoke-lhtb run-lhtb-roy

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

check: smoke-roy smoke-harbor
	./scripts/repo-status.sh --require-clean-submodules

smoke-roy:
	./scripts/smoke-roy.sh

smoke-roy-container:
	./scripts/smoke-roy-container.sh

smoke-harbor:
	./scripts/smoke-harbor.sh

smoke-lhtb:
	./scripts/smoke-lhtb.sh

run-lhtb-roy:
	./scripts/run-lhtb-roy.sh
