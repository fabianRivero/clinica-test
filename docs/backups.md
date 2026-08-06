# Database backup operations

This runbook covers scheduled backups, retention, status checks, and disaster recovery for the clinic database.

## Prerequisites

Install the PostgreSQL client on the application host. The `pg_dump` major version must match the PostgreSQL server major version.

```bash
sudo apt-get update
sudo apt-get install postgresql-client
pg_dump --version
sudo -u postgres psql -tAc 'SHOW server_version;'
```

The database role used by Django must be able to read all application data. Prefer a dedicated backup user when operationally possible. For PostgreSQL 14 and later, an administrator can grant read access with:

```sql
GRANT pg_read_all_data TO backup_user;
```

Store that user's credentials in `backend/.env`; never put passwords in cron entries, shell history, or this repository.

## Configure `BACKUPS_DIR`

Use a dedicated persistent mount with enough free space for at least two full dumps plus retained backups. The directory must not be served by nginx and must not be placed under `MEDIA_ROOT` or exposed through `MEDIA_URL`.

A shared production setup for a service running as `www-data`:

```bash
sudo install -d -o root -g www-data -m 0750 /var/lib/clinica/backups
```

For a dedicated service user, prefer ownership by that user and mode `0700`:

```bash
sudo install -d -o clinica -g clinica -m 0700 /var/lib/clinica/backups
```

Set the absolute path in `backend/.env`:

```dotenv
BACKUPS_DIR=/var/lib/clinica/backups
```

Confirm access before scheduling:

```bash
sudo -u www-data test -r /var/lib/clinica/backups
sudo -u www-data test -w /var/lib/clinica/backups
./scripts/backups.sh.example status
```

## Run and schedule backups

Test one backup interactively from the repository root:

```bash
sudo -u www-data /opt/clinica/scripts/backups.sh.example daily
```

Install this cron entry with `sudo crontab -e`. It runs every day at 03:05 and appends output to a dedicated log:

```cron
5 3 * * * www-data /opt/clinica/scripts/backups.sh.example daily >> /var/log/clinica-backups.log 2>&1
```

The helper loads `backend/.env`, invokes `python manage.py create_backup`, and returns the management command's exit status. The `weekly` subcommand exports `WEEKLY=1`; date-based weekly classification remains authoritative in the backup service.

```bash
./scripts/backups.sh.example weekly
./scripts/backups.sh.example status
```

### systemd timer alternative

For hosts standardized on systemd, create a oneshot service whose `ExecStart` is `/opt/clinica/scripts/backups.sh.example daily`, set `User=www-data` and `WorkingDirectory=/opt/clinica`, then pair it with an `OnCalendar=*-*-* 03:05:00` timer. Enable it with:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now clinica-backups.timer
sudo systemctl list-timers clinica-backups.timer
```

Systemd is preferable when centralized journald logs, retry policies, and dependency ordering are required.

## Retention

Defaults retain seven daily backups and four weekly backups. Override them in `backend/.env` when storage policy requires different values:

```dotenv
BACKUP_DAILY_KEEP=7
BACKUP_WEEKLY_KEEP=4
```

Retention runs after each successful backup. Before reducing either value, confirm the disaster-recovery policy and external/off-host copy schedule. Local retention is not a substitute for an encrypted off-site backup.

## Disaster recovery

Restoration is an operator procedure and is outside the application's runtime responsibilities. Stop application writes, take a safety snapshot of the target database, and verify the selected dump before proceeding.

Restore a PostgreSQL custom-format `.dump` file:

```bash
pg_restore --verbose --clean --if-exists --no-owner --no-privileges \
  --host=127.0.0.1 --port=5432 --username=clinica_app \
  --dbname=clinica /var/lib/clinica/backups/clinica_YYYY-MM-DD_HHMMSS.dump
```

If the target database does not exist, create it first with the expected owner. Run the restore with credentials authorized to recreate the required schema objects. After restoration, run application migrations and smoke tests before reopening traffic:

```bash
cd /opt/clinica/backend
./env/bin/python manage.py migrate
./env/bin/python manage.py check
```

Always rehearse restoration in an isolated environment. A backup that has never been restored is not yet proven recoverable.

## Troubleshooting

- **`pg_dump` not found:** install `postgresql-client`, verify the service user's `PATH`, and rerun the helper. The management command exits non-zero and records a failed trigger audit entry.
- **Client/server version mismatch:** install the client package matching the server's PostgreSQL major version.
- **Backup already running / HTTP 409:** another cron or manual operation holds the filesystem lock. Wait for it to finish; do not delete the lock file while a dump may be active.
- **Insufficient disk space:** run `./scripts/backups.sh.example status`, expand the mount or move verified backups off-host, then retry.
- **Permission denied:** verify directory ownership, mode, mount options, and that cron/systemd runs as the intended service user.

## Security and PHI

Database dumps contain protected health information (PHI), authentication data, and operational records. Access to `BACKUPS_DIR` must be limited to the service account and specifically authorized operators. Do not expose it over HTTP, place it in a shared home directory, attach it to support tickets, or copy it to unmanaged devices.

Encrypt off-host copies in transit and at rest, log operator access, rotate backup credentials, and define a secure deletion process consistent with the clinic's retention policy. Treat every `.dump` file with the same controls as the production database.
