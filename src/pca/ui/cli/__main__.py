"""Entry point so ``python -m pca`` and ``pca`` run the same CLI."""

from __future__ import annotations

from pca.ui.cli.app import app


def main() -> None:
    app()


if __name__ == "__main__":  # pragma: no cover - manual smoke test
    main()
