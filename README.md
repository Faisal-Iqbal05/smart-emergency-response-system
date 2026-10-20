# NeighbourAid

NeighbourAid is a mobile friendly community emergency coordination demo. Residents can submit and follow real database backed requests, link trusted contacts, and share updates with authorised guardians and responders. It is a coordination tool, not an emergency service. In India, call **112** directly for an immediate threat to life.

## What is implemented

- Django 5.2, Django REST Framework, JWT access/refresh authentication with refresh token blacklist, OpenAPI docs, filtering, pagination, and request throttling.
- A custom user model with resident, guardian, volunteer, security, and coordinator roles. Public registration always creates a resident.
- Communities, blocks, flats, resident mappings, guardian consent/verification, volunteer profiles, incidents, assignments, audit events, incident updates, in-app notifications, and delivery attempt records.
- Accessible responsive pages for home, registration/login/password reset, resident dashboard, help request, incident history/detail, contacts, profile, notifications, volunteers, and coordinator command.
- Incident creation with optional browser location and typed locality fallback, server confirmation, unique reference, location range checks, guardian/coordinator notification records, incident history, cancellation, and legal status transitions.
- Single active volunteer assignment with a database uniqueness constraint and transaction-based claim flow.
- Idempotent escalation command. Run `process_escalations` periodically using Windows Task Scheduler or cron; it is not an always-running worker.
- PWA manifest, local SVG icons, offline page, network status, and static/public-only caching. Authenticated pages, APIs, admin, and incident pages are excluded from the cache. Offline submissions are not stored or described as delivered.
- Demo data command creates fictional accounts only when explicitly invoked.

## Project structure

```text
config/                 Django settings, URL configuration, ASGI/WSGI
core/                   Models, views, API, services, admin, tests, commands
core/migrations/        Initial custom-user schema migration
templates/              Shared shell and role-aware pages
templates/registration/ Django auth templates
static/css,js,icons/    Local design, PWA scripts, local icons
manage.py
requirements.txt
.env.example
```

## Requirements and installation (Windows PowerShell)

Python 3.11 or later is recommended. PostgreSQL is the intended deployment database; SQLite is the local demo default. To set up in this workspace:

```powershell
cd "C:\Users\fsyed\Desktop\Web App"
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Open <http://127.0.0.1:8000/>. API docs are at <http://127.0.0.1:8000/api/docs/> and the raw OpenAPI schema at `/api/schema/`. Django admin is at `/admin/`.

### PostgreSQL configuration

Install PostgreSQL and create a database and role. In `.env`, set a strong private `SECRET_KEY`, set `DEBUG=false`, add deployment hostnames to `ALLOWED_HOSTS`, and set:

```dotenv
DATABASE_URL=postgresql://neighbouraid:YOUR_PASSWORD@localhost:5432/neighbouraid
```

Do not commit `.env`. The provided `DATABASE_URL=sqlite:///db.sqlite3` is a conscious local fallback, not the production default. For a TLS-only deployment, set `SECURE_SSL_REDIRECT=true` and `SECURE_HSTS_SECONDS=31536000` after verifying HTTPS and proxy forwarding. HSTS subdomain/preload options are separate opt-ins. Never run with `DEBUG=true` in production.

To run a local PostgreSQL service with Docker Compose, set `POSTGRES_PASSWORD` in `.env`, change `DATABASE_URL` to the PostgreSQL URL above, then run `docker compose up -d db`. Wait for the `db` health check before migrating.

### Demo accounts

Optional. Use a memorable temporary password (10+ characters) and change it before any shared demo:

```powershell
python manage.py seed_demo --password "Local-Demo-Pass-Change-Me-7"
```

Accounts: `demo-resident`, `demo-guardian`, `demo-volunteer`, and `demo-coordinator`. The resident can add the guardian by email. Guardian notifications require coordinator verification in Django admin. No sample incidents are created.

## API quick start

- `POST /api/v1/auth/register/` — public resident registration.
- `POST /api/v1/auth/token/` and `/api/v1/auth/token/refresh/` — JWT login and refresh (rotated refresh tokens are blacklisted).
- `GET/PATCH /api/v1/me/` — own profile; role is read-only.
- `POST /api/v1/auth/logout/` — blacklist the submitted refresh token.
- `GET/POST /api/v1/incidents/` — scoped list and resident submission.
- `GET /api/v1/incidents/{uuid}/`, `/timeline/`, `/updates/`; `POST /cancel/`, `/acknowledge/`, `/accept/`, `/assign/`, `/status_update/` as role and state permit.
- `/api/v1/guardians/`, `/api/v1/notifications/`, and `/api/v1/volunteer/profile/` — own contacts, notifications, and volunteer settings.
- OpenAPI explorer: `/api/docs/`.

Web sessions use Django CSRF protection. The API supports JWT and session authentication. Avoid putting JWTs in browser local storage in a production frontend; this demo’s browser forms use Django sessions.

## Escalation and notifications

In-app alerts are saved as `Simulated`, with a notification attempt record. This does not mean email or SMS was sent. Email password reset uses Django's console backend in development. No SMS, push, or external email provider is configured. For periodic escalation checks, schedule:

```powershell
python manage.py process_escalations
```

The command processes overdue, unacknowledged requests once. Run it every minute or another chosen interval with Task Scheduler. A worker such as Celery/Redis and real outbound delivery providers remain future integrations.

## Tests and checks

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test
```

Tests cover registration/invalid payloads, JWT login, profile role protection, incident validation and manual locations, resident IDOR restrictions, coordinator scoping, guardian visibility, cancellation/state transitions, exclusive volunteer claims, escalation idempotency and simulated delivery, pagination/filtering, auth pages, PWA assets, and coordinator page access.

## Demo walk-through

1. Register a resident and sign in. Submit a categorized request with a typed locality (geolocation is optional).
2. Note the `NA-...` reference and verify the incident timeline and status.
3. Use a second account and add its registered email as a trusted contact. In admin, verify the relationship; generated guardian messages then appear as simulated in-app notifications.
4. Create/verify a volunteer profile and coordinator account via admin or the demo command. Set volunteer availability, then accept an open incident.
5. As coordinator, review incidents and records from `/command/`; use admin for operational verification and audit records.
6. For escalation demonstration, set an incident `escalation_due_at` in the past in admin and run `python manage.py process_escalations` twice. The second run should create no duplicate attempt.

## Viva guide

- **Architecture:** Django serves HTML and a versioned REST API. Views handle HTTP; serializers validate API inputs; `services.py` holds incident transactions and state rules; models store relational data.
- **Important models:** `User`, `Society/Block/Flat`, `GuardianRelationship`, `VolunteerProfile`, `Incident`, `IncidentAssignment`, `AuditEvent`, `IncidentUpdate`, and `Notification`.
- **Authentication and permissions:** Django sessions protect forms with CSRF. The API uses JWT. Querysets are scoped by role and resident ownership; user-editable profile fields cannot change the role.
- **SOS flow:** The server validates required category/description and optional coordinates, saves an incident and audit event in one transaction, then records simulated alerts. The user sees confirmation only after saving succeeds.
- **Escalation:** Each request has a due time and processed flag. The management command selects due unacknowledged incidents and marks each once, so repeated scheduler runs do not create duplicate secondary alerts.
- **Assignment:** A transaction locks the incident row and a conditional unique database constraint permits one active assignment.
- **Testing:** Django's test runner exercises validation, permissions, state transitions, assignment exclusivity, escalation, API filtering, and route availability.

## Limitations and follow-up work

- The workspace initially contained no project files, and the remote was empty. This implementation was committed and pushed to the configured GitHub repository as the initial `main` branch.
- Society mapping and guardian verification are intentionally managed by an administrator/coordinator through Django admin; a full membership approval workflow is not built.
- There is no automatic coordinator assignment UI, security-specific workflow, status action controls on the coordinator page, CSV export, search box UI, decline/reassignment flow, or real-time chat; API and model support is partial for these workflows.
- Email, SMS, and push delivery require credentials, provider adapters, retry/backoff workers, and delivery verification. Current notifications are explicitly simulated.
- Escalation requires an external scheduler to invoke the documented command. SQLite does not support PostgreSQL's row locking behavior; use PostgreSQL for multi-worker deployment.
- The PWA uses SVG icons for modern browsers and caches only static assets and the public offline page. Installability varies by browser; geolocation needs HTTPS outside localhost.
- Incident retention/deletion policy and legal review should be established by the deploying community. Avoid entering unnecessary personal or medical details.

## Requirements map

| Requirement area | Implementation |
| --- | --- |
| Accounts and profiles | Custom user, resident registration, login/logout/password reset/change, profile page, role locked on public signup |
| Community and guardians | Society/block/flat/mapping/relationship models, admin management, consent and verification gates |
| SOS and lifecycle | API/web submission, optional coordinates or locality, reference, history, transitions, cancellation, audit |
| Guardians/escalation | Primary/secondary contact rules, simulated in-app alert, scheduled idempotent command |
| Volunteers | Verified availability, eligible open list, transactional accept, single active assignment constraint |
| Notifications/updates | In-app simulated state and attempts, incident update thread |
| Coordinator/reports | Scoped dashboard and live DB status summaries, category/status filters, Django admin audit |
| API/security | JWT, scoped querysets, CSRF web forms, throttling, filter/pagination, OpenAPI |
| PWA/accessibility | Manifest, local icons, offline state/page, keyboard focus, semantic labels, responsive CSS, reduced motion |
| QA/documentation | Automated Django tests, environment files, migration, demo command, setup and viva guide |
