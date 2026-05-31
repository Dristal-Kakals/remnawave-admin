# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Remnawave Admin is a monorepo containing three integrated components for managing Remnawave VPN panel:

1. **Telegram Bot** (`src/`) - Python/aiogram bot for admin operations
2. **Web Backend** (`web/backend/`) - FastAPI REST API
3. **Web Frontend** (`web/frontend/`) - React + TypeScript SPA

All three share a common PostgreSQL database and use a `shared/` module for reusable code.

## Architecture

### Shared Module (`shared/`)

Critical shared components used by both bot and web backend:

- **`database.py`** - AsyncPG connection pool, all DB operations (users, nodes, hosts, violations, connections, IP metadata)
- **`api_client.py`** - HTTP client for Remnawave Panel API (handles auth, retries, rate limiting)
- **`config_service.py`** - Dynamic configuration (DB-first, then .env fallback)
- **`logger.py`** - Structlog-based logging (JSON output, processor pipeline)
- **`sync.py`** - Background sync service (Panel API → local DB cache)
- **`connection_monitor.py`** - Active connection tracking and stats (used by violation detector)
- **`violation_detector.py`** - Multi-factor abuse detection (5 analyzers: temporal, geo, ASN, profile, device)
- **`db_schema.py`** - Admin table/column constants (`ADMIN_TABLE`, `ADMIN_COLUMNS`, `ADMIN_COUNTER_COLUMNS`, etc.)
- **`db_query.py`** - Generic SQL builders (`select_sql`, `insert_sql`, `update_sql`, `delete_sql`) and JOIN helpers (`left_join_sql`, `join_sql`)
- **`admin_quota.py`** - Shared helpers for admin counter updates (`apply_user_delete_quotas`, `apply_user_reassign_quotas`, `apply_user_reset_traffic_quotas`, batch versions). Centralizes the logic for incrementing/decrementing `users_created` and `traffic_used_bytes` so bot and web backend stay in sync.

**Key principle**: Bot and web backend MUST NOT duplicate logic. Common operations go in `shared/`.

### Telegram Bot (`src/`)

Entry point: `src/main.py`

- **Handlers** (`src/handlers/`) - User-facing commands (users, nodes, hosts, billing, reports, violations)
- **Services** (`src/services/`) - Business logic:
  - `violation_detector.py` - Re-export from `shared/` (backward compat)
  - `webhook.py` - FastAPI app receiving events from Panel
  - `report_scheduler.py` - Scheduled violation reports
  - `health_check.py` - Panel health monitoring
- **Keyboards** (`src/keyboards/`) - Inline keyboard generators
- **Utils** (`src/utils/`) - i18n, auth middleware

### Web Backend (`web/backend/`)

Entry point: `web/backend/main.py`

Structure:
```
web/backend/
├── api/v2/          # REST endpoints (users, nodes, hosts, violations, analytics, roles, mailserver, collector)
├── core/            # Config, security, auth, permissions, audit middleware, violation notifier
├── schemas/         # Pydantic models
└── tests/           # Pytest test suite
```

**Important**: All API endpoints are under `/api/v2/`. No `/api/v1/` exists.

RBAC system in `core/permissions.py`:
- Resources: users, nodes, hosts, violations, settings, fleet, analytics, admins, roles, audit, logs, automation, notifications, resources
- Actions: view, create, edit, delete, bulk_operations, resolve, run

### Web Frontend (`web/frontend/`)

Stack: React 18 + TypeScript + Vite + TailwindCSS + shadcn/ui

Key directories:
- `src/pages/` - Page components (Dashboard, Users, Nodes, Settings, SystemLogs, etc.)
- `src/components/` - Reusable UI (PermissionGate, ConfirmDialog, layout)
- `src/api/` - Axios client + API functions
- `src/stores/` - Zustand state management (auth, filters, theme)

**State management**:
- React Query (`@tanstack/react-query`) for server state
- Zustand for client state (auth tokens, theme, locale)

## Development Commands

### Bot Development

```bash
# Local development
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python -m src.main

# Run tests
pytest                          # All tests
pytest src/tests/              # Bot tests only
pytest -v -s                   # Verbose with stdout
pytest --cov=src --cov-report=html  # Coverage report

# Database migrations
alembic revision --autogenerate -m "description"  # Create migration
alembic upgrade head                              # Apply migrations
alembic downgrade -1                              # Rollback one
```

### Web Backend Development

```bash
cd web/backend

# Install dependencies
pip install -r requirements.txt

# Run locally (hot reload)
uvicorn main:app --reload --port 8081

# Run tests
pytest                                  # All tests
pytest tests/test_auth.py              # Specific file
pytest -k "test_login"                 # Specific test
pytest --cov=web.backend --cov-report=html  # Coverage

# Type checking (if using mypy)
mypy web/backend --ignore-missing-imports
```

### Web Frontend Development

```bash
cd web/frontend

# Install dependencies
npm install

# Development server (hot reload on :3000)
npm run dev

# Type checking
npm run typecheck

# Linting
npm run lint

# Tests
npm test                    # Unit tests (Vitest)
npm run test:watch          # Watch mode
npm run test:coverage       # Coverage report
npm run test:e2e            # Playwright E2E tests
npm run test:e2e:headed     # E2E with browser visible
npm run test:e2e:ui         # E2E with Playwright UI

# Build
npm run build               # Production build
npm run build:check         # Type check + build
```

### Docker Development

```bash
# Build images
docker compose build

# Run bot only
docker compose up -d

# Run bot + web panel
docker compose --profile web up -d

# View logs
docker compose logs -f bot
docker compose logs -f web-backend
docker compose logs -f web-frontend

# Restart specific service
docker compose restart bot

# Run migrations in container
docker exec -it <container_name> alembic upgrade head

# Admin CLI (reset password, create superadmin)
docker exec -it <container_name> python3 scripts/admin_cli.py list-admins
docker exec -it <container_name> python3 scripts/admin_cli.py reset-password --username admin
docker exec -it <container_name> python3 scripts/admin_cli.py create-superadmin --username newadmin
```

## Key Patterns

### Data Flow: Violations & Analytics

1. **Node Agent** → sends connection data → **Web Backend Collector API** (`/api/v2/collector/batch`)
2. **Collector** → runs `ViolationDetector` (from `shared/`) → stores in DB (`violations` table)
3. **Collector** → sends notifications via `notification_service` (Telegram, in-app)
4. **Web Backend** → exposes `/api/v2/violations/*` endpoints for UI
5. **Web Frontend** → fetches data → displays in UI

**Critical**: Node Agent sends data directly to Web Backend (port 8081), NOT to the bot. The bot no longer has a collector endpoint. The `AGENT_COLLECTOR_URL` in node-agent `.env` must point to the web backend.

### Authentication Flow

1. **Frontend** → Telegram Login Widget → redirects to `/api/v2/auth/telegram-callback`
2. **Backend** → validates Telegram hash → checks `admins` table → issues JWT
3. **Frontend** → stores tokens in Zustand → includes in Authorization header
4. **Backend** → validates JWT → checks RBAC permissions → allows/denies

### Configuration Priority

Settings loaded in this order (first wins):
1. Database (`settings` table via `config_service`)
2. Environment variables (`.env`)
3. Hardcoded defaults

**To change settings**: Use web UI (Settings page) or bot (`/config` command). Changes persist to DB and apply immediately without restart.

### Admin SQL Query Pattern

When building SQL for admin tables (`admin_accounts`, `admin_roles`, `admin_permissions`, `admin_audit_log`, `admin_devices`, `admin_access_policies`):

- **Always use the generic builders** from `shared/db_query.py` (`select_sql`, `insert_sql`, `update_sql`, `delete_sql`) instead of raw SQL strings.
- **Always use table/column constants** from `shared/db_schema.py` (`ADMIN_TABLE`, `ADMIN_COLUMNS`, `ADMIN_INSERT_COLUMNS`, etc.) instead of hardcoding names.
- **JOIN helpers** (`left_join_sql`, `join_sql`) for composing JOIN clauses into the `suffix` parameter of `select_sql`.
- Each argument goes on its own line (multi-line format) for consistency with the function definitions.

Example:
```python
from shared.db_schema import ADMIN_TABLE, ADMIN_ROLES_TABLE
from shared.db_query import select_sql, left_join_sql

cols = "a.*, r.name as role_name"
join = f"a {left_join_sql(ADMIN_ROLES_TABLE, 'r', 'r.id = a.role_id')}"
row = await conn.fetchrow(
    select_sql(ADMIN_TABLE, cols, f"{join} WHERE a.id = $1"),
    admin_id,
)
```

### Database Schema

Critical tables:
- `users` - Cached user data from Panel API
- `nodes` - Node data + agent tokens + system metrics (CPU, RAM, disk)
- `hosts` - Host configurations
- `violations` - Detected abuse (multi-factor scoring)
- `user_connections` - Connection history (for temporal analysis)
- `ip_metadata` - GeoIP + ASN data (city, country, provider type)
- `settings` - Dynamic configuration KV store
- `admins` - Web panel admin accounts (bcrypt passwords)
- `roles` - RBAC roles with permissions matrix

### Admin Counter Model

The `admins` table tracks per-admin usage counters via `shared/admin_quota.py` helpers:

| Counter | Purpose | Where used |
|---------|---------|------------|
| `users_created` | Lifetime events counter (increments on both create AND delete) | All user/node/host operations |
| `traffic_used_bytes` | Currently allocated traffic quota (sum of `trafficLimitBytes` of owned users) | All user traffic operations |
| `nodes_created` | Lifetime events counter | Node create + delete |
| `hosts_created` | Lifetime events counter | Host create + delete |

**Counter update rules:**

- **User create** (with limit): creator's `users_created` +1, `traffic_used_bytes` +limit
- **User create** (unlimited): creator's `users_created` +1, traffic unchanged
- **User edit traffic up**: acting admin's `traffic_used_bytes` +delta
- **User edit traffic down**: acting admin's `traffic_used_bytes` -delta
- **User delete** (single/bulk): owner's `users_created` +1, `traffic_used_bytes` -unused
- **User reassign** (had previous owner): old admin -1 users_created and -unused traffic, new admin +1 and +unused
- **User reassign** (no previous owner): new admin +1 users_created and +full_limit traffic
- **User traffic reset** (single/bulk/all): creator's `traffic_used_bytes` +used_bytes
- **User revoke**: no counter change
- **Node/host create**: acting admin's counter +1
- **Node/host delete**: acting admin's counter +1
- **Counter reset** (superadmin manual): target counter → 0

**Where to put counter logic**: All counter update code lives in `shared/admin_quota.py`. Bot and web backend call these helpers — they MUST NOT call `increment_usage_counter` directly with custom logic. The helpers handle aggregation (per-admin sums), per-user data extraction, and the correct sign/direction for each operation.

Available helpers in `shared/admin_quota.py`:
- `fetch_user_quota_data(uuid)` / `fetch_users_quota_data_batch(uuids)` — fetch creator + traffic from local DB
- `apply_user_delete_quotas(creator_id, limit, used)` — single delete
- `apply_users_delete_quotas_batch(users_data)` — bulk delete (aggregates per admin)
- `apply_user_reassign_quotas(prev_id, new_id, limit, used)` — single reassign
- `apply_users_reassign_quotas_batch(users_data, new_id)` — bulk reassign
- `apply_user_reset_traffic_quotas(creator_id, used)` — single traffic reset
- `apply_users_reset_traffic_quotas_batch(users_data)` — bulk traffic reset

### Anti-Abuse System

`ViolationDetector` uses 5 analyzers:
1. **TemporalAnalyzer** - Simultaneous connections, rapid switching
2. **GeoAnalyzer** - Impossible travel detection
3. **ASNAnalyzer** - VPN/datacenter/mobile classification
4. **ProfileAnalyzer** - Deviation from user's normal behavior
5. **DeviceAnalyzer** - HWID fingerprint analysis

Outputs `ViolationScore` with confidence + recommended action (no_action, monitor, warn, soft_block, temp_block, hard_block).

## Common Gotchas

### Memory Usage

User preferences stored in memory:
- **Язык общения**: Всегда отвечать на русском языке (см. `.claude/projects/.../memory/MEMORY.md`)
- **No Co-Authored-By**: Не добавлять `Co-Authored-By: Claude` в коммиты

### Frontend Type Safety

When adding new API endpoints:
1. Update backend schemas in `web/backend/schemas/`
2. Add TypeScript types in `web/frontend/src/api/` (NOT auto-generated)
3. Always use `Array.isArray()` before `.map()` / `.reduce()` - API can return non-array values

Common error patterns:
- `w.reduce is not a function` → Missing `Array.isArray()` check
- `Unknown resource: X` → Add resource to `AVAILABLE_RESOURCES` in `web/backend/api/v2/roles.py`

### Logging

**Bot** logs to:
- Console: WARNING+ only
- Files: `logs/adminbot_INFO.log` (all), `logs/adminbot_WARNING.log` (errors)

**Web Backend** logs to:
- Console: WARNING+ only
- Files: `logs/web_INFO.log` (all), `logs/web_WARNING.log` (errors)

**Structlog format**: JSON lines with `timestamp`, `level`, `event`, `logger`, and extra context.

### Mobile Responsive Design

SystemLogs and other admin pages MUST be mobile-friendly:
- Use `whitespace-pre-wrap` for log messages (preserve line breaks like Postgres logs)
- Use `break-words` not `break-all` (respect word boundaries)
- Add `overflow-x-auto` on containers to prevent horizontal overflow
- Use responsive classes: `text-xs sm:text-sm`, `min-h-[250px] md:min-h-[400px]`

## Testing

### Backend Tests

Pytest fixtures in `web/backend/tests/conftest.py`:
- `test_db` - AsyncPG connection to test database
- `client` - HTTPX async client for API testing
- `auth_headers` - Admin JWT token headers

Example:
```python
async def test_list_users(client, auth_headers):
    response = await client.get("/api/v2/users", headers=auth_headers)
    assert response.status_code == 200
```

### Frontend Tests

Vitest for unit/integration:
- Uses `@testing-library/react` for component testing
- Mock API calls with `vi.mock()`

Playwright for E2E:
- Tests in `web/frontend/tests/` (if exists) or `web/frontend/e2e/`
- Run with `npm run test:e2e`

## Git Workflow

**Primary branch**: `main`
**Development branch**: `dev`

**Commit message format**:
```
type: brief description

Optional body explaining what and why.
```

Types: `feat`, `fix`, `refactor`, `docs`, `test`, `chore`

**No Co-Authored-By tags** - user preference.

## Environment Variables

Critical variables (see `.env.example` for full list):

**Bot**:
- `BOT_TOKEN` - Telegram bot token (required)
- `API_BASE_URL` - Remnawave Panel URL (required)
- `API_TOKEN` - Panel API token (required)
- `ADMINS` - Comma-separated Telegram IDs (required)
- `DATABASE_URL` - PostgreSQL connection string
- `BOT_CALLBACK_URL` - Base URL for bot webhook callbacks (used by collector for violation notifications)

**Web**:
- `WEB_SECRET_KEY` - JWT secret (required for web profile)
- `TELEGRAM_BOT_USERNAME` - Bot username for Login Widget (required for web profile)
- `WEB_CORS_ORIGINS` - Allowed origins for CORS
- `INTERNAL_API_SECRET` - Shared secret for bot→backend proxy mode (enables RBAC/quota/audit on internal API calls)
- `INTERNAL_API_BACKEND_URL` - Backend URL for proxy mode (default: `http://web-backend:8081`)

**Shared**:
- `MAXMIND_LICENSE_KEY` - GeoIP database auto-download (optional, fallback to ip-api.com)
- `MAIL_SERVER_ENABLED` - Built-in SMTP server toggle
- `WEBHOOK_SECRET` - HMAC signature verification for webhooks

## Resources

- [README.md](README.md) - Quick start, deployment
- [web/README.md](web/README.md) - Web panel setup, reverse proxy examples
- [docs/anti-abuse.md](docs/anti-abuse.md) - Violation detection system details
- [WEBHOOK_SETUP.md](WEBHOOK_SETUP.md) - Webhook configuration guide
