# Benchmark adapters

Each benchmark lives in its own directory and adapts that benchmark to Roy's public
CLI or library interface. Benchmark-specific behavior must not be added to Roy.

Every adapter must document installation, a cheap smoke test, a full run, result
locations, and the exact commits used.
