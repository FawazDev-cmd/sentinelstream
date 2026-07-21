# Development Rules

- Use Python 3.13 and manage dependencies with uv.
- Keep public and test code typed; `uv run mypy app tests` must pass in strict mode.
- Run pytest, Ruff linting, Ruff formatting checks, and mypy before completing a
  milestone.
- Use the standard logging library unless an explicit later decision changes it.
- Keep settings centralized and use the `SENTINELSTREAM_` environment prefix.
- Preserve dependency direction and keep domain code framework-independent.
- Do not create speculative packages, abstractions, settings, or integrations.
- Keep tests deterministic and exercise real application boundaries.
- Describe future capabilities as planned, never as implemented.
- Do not commit or push unless explicitly requested.
