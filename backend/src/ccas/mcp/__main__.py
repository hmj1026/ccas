"""Module entry point for ``python -m ccas.mcp``."""

from ccas.mcp.server import main

if __name__ == "__main__":  # pragma: no cover - exercised by subprocess tests
    main()
