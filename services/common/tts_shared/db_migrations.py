from __future__ import annotations

from argparse import ArgumentParser
from pathlib import Path

from alembic import command
from alembic.config import Config

from .config import get_settings


def migrations_dir() -> Path:
    return Path(__file__).resolve().parent / "migrations"


def get_alembic_config(database_url: str | None = None) -> Config:
    settings = get_settings()
    config = Config()
    config.set_main_option("script_location", str(migrations_dir()))
    config.set_main_option("sqlalchemy.url", database_url or settings.database_url)
    return config


def run_migrations(target_revision: str = "head") -> None:
    command.upgrade(get_alembic_config(), target_revision)


def main() -> None:
    parser = ArgumentParser(description="Run NAC-TTS database migrations.")
    parser.add_argument("command", choices=["upgrade"], help="Migration command to run.")
    parser.add_argument("revision", nargs="?", default="head", help="Target revision for upgrade.")
    args = parser.parse_args()

    if args.command == "upgrade":
        run_migrations(args.revision)


if __name__ == "__main__":
    main()
