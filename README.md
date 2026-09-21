# Telos-X

Telos-X is a Telegram-based Cyber Threat Intelligence pipeline. It discovers
configured Telegram groups, stores groups and exposed members, selectively
profiles configured users, processes batch and realtime messages, translates
text, runs Finder and LR/BERT analysis, persists results, and routes alerts to
configured Discord or Slack notifiers.

## Requirements

- Python 3.10, 3.11, or 3.12
- Poetry 2.x
- Telegram API credentials for live Telegram operations

The application runs without BERT or the local CTranslate2 model. Install the
optional extras only when their model artifacts are available:

```console
poetry install --extras bert
poetry install --extras local-translation
```

## Setup

```console
poetry install
copy config.example.ini config.local.ini
poetry run python -m telos_x --help
```

On Debian, replace `copy` with `cp`. Put private credentials and webhook URLs
only in the local configuration file; do not commit that file. Relative
`data_path` and `groups_file` values are resolved from the configuration file's
directory. The repository-level `groups.csv` is the default discovery input.

Typical operations are:

```console
poetry run python -m telos_x connect --config config.local.ini
poetry run python -m telos_x load_groups --config config.local.ini
poetry run python -m telos_x download_messages --config config.local.ini
poetry run python -m telos_x listen --config config.local.ini
```

Run `python -m telos_x --help` for every report, export, graph, statistics, and
maintenance action. Telegram group joining and external notification delivery
are real external operations; use controlled accounts and endpoints.

## Database migrations

Pass the configured data directory explicitly when migrating an existing DB:

```console
poetry run alembic -x data_path=/srv/telos-x/data upgrade head
```

Without an override, Alembic uses the deterministic repository `data/`
directory. It never recreates an existing database automatically.

## Local verification

```console
poetry check
poetry run python -m compileall telos_x
poetry run pytest
tox config
```

The default tox matrix covers Python 3.10 through 3.12. Publishing is available
only through the explicit `tox -e deploy` environment.

## License and lineage

Telos-X is distributed under the Apache License 2.0. See `LICENSE`. Historical
OSIx attribution retained in source files reflects the project's upstream
lineage.
