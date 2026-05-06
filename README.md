# Domain Cleanup Automation

Automatically detects expired / quarantined domains from HostingIndustries, updates the Linkstatus source database, generates grouped email drafts for responsible admins, and provides a full audit trail with dashboard.

## Quick Start

```bash
# 1. Copy and fill in configuration
cp .env.example .env
# Edit .env — fill in HostingIndustries credentials, source DB info, etc.

# 2. Build and start the dashboard
docker compose build
docker compose up -d dashboard

# 3. Run the audit DB migration (first time only — uses existing mysql_db container)
PYTHONPATH=. python3 -m alembic upgrade head

# 4. Execute a dry-run
docker compose run --rm runner run-all --dry-run

# 5. Open the dashboard
open http://localhost:8088   # login: admin / changeme (configure in .env)
```

### Server Setup

The audit database (`domain_audit`) is hosted on the existing `mysql_db` container that already runs on this server. No separate MySQL container is needed. The domain-cleanup containers connect via the `mysql-database_default` Docker network.

## CLI Commands

```bash
python -m app.main fetch-domains          # Fetch domain list only
python -m app.main check-domains          # Check + classify statuses
python -m app.main generate-email-drafts  # Generate drafts for affected orders
python -m app.main cleanup-openorders     # Delete affected orders (respects DRY_RUN)
python -m app.main run-all --dry-run      # Full pipeline, dry-run
python -m app.main run-all --no-dry-run   # Full pipeline, live
python -m app.main dashboard              # Start dashboard web server
```

## Architecture

```
HostingIndustries  →  Parser  →  Matcher  →  Label Updates
    (1-2 accounts)                          →  Order Cleanup
                                            →  Email Drafts → Mailgun
                                            →  Audit DB → Dashboard
```

## Configuration

All settings are in `.env`. Key sections:

| Section | Variables |
|---------|-----------|
| Source DB (Linkstatus) | `SOURCE_DB_HOST`, `SOURCE_DB_PORT`, `SOURCE_DB_NAME`, `SOURCE_DB_USER`, `SOURCE_DB_PASSWORD` |
| Audit DB (local) | `AUDIT_DB_HOST`, `AUDIT_DB_PORT`, `AUDIT_DB_NAME`, `AUDIT_DB_USER`, `AUDIT_DB_PASSWORD` |
| HostingIndustries 1 | `HI_ACCOUNT1_USERNAME`, `HI_ACCOUNT1_PASSWORD`, `HI_ACCOUNT1_NAME` |
| HostingIndustries 2 | `HI_ACCOUNT2_USERNAME`, `HI_ACCOUNT2_PASSWORD`, `HI_ACCOUNT2_NAME` |
| Dashboard | `DASHBOARD_USERNAME`, `DASHBOARD_PASSWORD`, `DASHBOARD_PORT` |
| Mailgun | `ENABLE_EMAIL_SEND`, `MAILGUN_API_KEY`, `MAILGUN_DOMAIN`, `MAILGUN_FROM`, `MAILGUN_API_URL` |
| Google Sheets | `ENABLE_SHEETS_SYNC`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SPREADSHEET_ID`, `GOOGLE_WORKSHEET_NAME` |
| Business rules | `UNUSABLE_DOMAIN_STATUSES`, `AFFECTED_ORDER_STATUSES`, `EXPIRED_LABEL_ID` |

## Dry-Run Mode

**Default: enabled.** When `DRY_RUN=true`:
- Labels are NOT updated in the source database
- Open orders are NOT deleted
- Email drafts are generated and saved to disk but not sent
- All intended actions are recorded in the audit database

To enable real writes: set `DRY_RUN=false` or use `--no-dry-run`.

## Dashboard

Basic-auth protected web UI at the configured port. Pages:
- **Overview** — recent runs with stats, manual trigger buttons
- **Run Detail** — full breakdown per run
- **Domains** — searchable domain history
- **Orders** — searchable order history
- **Email Drafts** — all generated drafts with send status
- **Logs** — filterable log entries

## Scheduling (cron)

```cron
# Daily dry-run at 06:00
0 6 * * * cd /home/user/projecten/expired_domains && docker compose run --rm runner run-all --dry-run >> /var/log/domain-cleanup.log 2>&1

# Weekly live run on Monday at 07:00
0 7 * * 1 cd /home/user/projecten/expired_domains && docker compose run --rm runner run-all --no-dry-run >> /var/log/domain-cleanup.log 2>&1
```

## Enabling Real Cleanup

1. Run in dry-run mode first and review via the dashboard
2. Set `DRY_RUN=false` in `.env`
3. Optionally enable Mailgun: set `ENABLE_EMAIL_SEND=true` and fill in `MAILGUN_API_KEY`
4. Run `python -m app.main run-all`

## Running Tests

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Project Structure

```
app/
  main.py                    # CLI entrypoint
  config.py                  # Pydantic settings
  logging_config.py          # Structured logging
  clients/
    hostingindustries.py     # Scraper + parser
    source_db.py             # Source DB models
    audit_db.py              # Audit DB models
  repositories/
    domains_repository.py
    domlabels_repository.py
    openorders_repository.py
    admin_repository.py
    customer_repository.py
    audit_repository.py
  services/
    run_coordinator.py       # Full pipeline orchestration
    email_draft_service.py   # Draft generation + grouping
    mailgun_service.py       # Mailgun HTTP API
    report_service.py        # JSON/CSV reports
  dashboard/
    app.py                   # FastAPI app factory
    routes.py                # All dashboard routes
    templates/               # Jinja2 templates
  templates/
    expired_domain_orders_email.html
  utils/
    domain_normalization.py
tests/
alembic/
Dockerfile
docker-compose.yml
requirements.txt
.env.example
```
