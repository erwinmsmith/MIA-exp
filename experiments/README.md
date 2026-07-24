# Benchmark adapters

Each benchmark lives in its own directory and adapts that benchmark to Roy's public
CLI or library interface. Benchmark-specific behavior must not be added to Roy.

Every adapter must document installation, a cheap smoke test, a full run, result
locations, and the exact commits used.

The registry in `experiments/benchmarks.json` is the source of truth for data
locations, upstream commits, checksums, sizes, and primary metrics. All adapters
must map their native result into the common `earned / possible` score contract
without discarding native details.
