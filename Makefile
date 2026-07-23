SHELL := /bin/bash

.PHONY: bootstrap bundle doctor repo-status check smoke-roy smoke-harbor smoke-lhtb

bootstrap:
	./scripts/bootstrap.sh

bundle:
	./scripts/build-roy-bundle.sh

doctor:
	./scripts/doctor.sh

repo-status:
	./scripts/repo-status.sh

check: smoke-roy smoke-harbor
	./scripts/repo-status.sh --require-clean-submodules

smoke-roy:
	./scripts/smoke-roy.sh

smoke-harbor:
	./scripts/smoke-harbor.sh

smoke-lhtb:
	./scripts/smoke-lhtb.sh
