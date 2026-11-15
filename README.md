# Django task manager

A complete server-rendered Django application with user authentication and private
task CRUD. Uses Django 5.2 LTS, SQLite locally, PostgreSQL on Render, and WhiteNoise
for production CSS. No frontend build tools or third-party CDN assets are needed.

## Features

- Signup with Django password validation and hashed passwords.
- Login with safe return-to-page redirects; POST-only logout.
- Create, list, view, edit, and delete tasks.
- Title, description, status, optional due date, and timestamps.
- Per-user ownership enforced on the server; another user's task IDs return 404.
- Paginated task list, responsive HTML/CSS, validation errors, and flash messages.
- CSRF protection on every mutation and template autoescaping for user content.
- Django admin for trusted staff to manage users and all tasks.
- Database-aware health endpoint, deployment configuration, and automated tests.

## 1. Run locally (Windows PowerShell)

Install Python 3.12 or newer, preferably the latest supported security release.
The deployment configuration selects the latest Python 3.12 patch release.

Open PowerShell in this project directory:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
$secret = & .\.venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
(Get-Content .env) -replace '^DJANGO_SECRET_KEY=.*$', "DJANGO_SECRET_KEY=$secret" | Set-Content .env
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py createsuperuser
.\.venv\Scripts\python.exe manage.py runserver
```

Stop if a command fails and resolve its error before continuing. If `.venv`
already exists, skip its creation and reuse it. If `.env` already exists, do not
overwrite it: keep its existing secret and update its settings as needed.

This does not require activating the virtual environment or changing PowerShell's
execution policy. Gunicorn is deliberately installed only on non-Windows hosts;
Windows development uses Django's development server.

Open <http://127.0.0.1:8000/accounts/signup/> to create a normal account, log in,
then create a task. Use <http://127.0.0.1:8000/admin/> with the superuser account.
Stop the development server with Ctrl+C.

The generated `.env` and local database are ignored by Git. Do not share secrets
or commit either file. Local development uses SQLite automatically when
`DJANGO_DEBUG=True` and `DATABASE_URL` is empty.

### Tests

After configuring `.env`:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test tasks
```

The tests cover signup/password validation, login/logout, safe redirects, private
task access, CRUD, validation, optional dates, pagination, escaped user content,
CSRF rejection, and health-check failures. Tests use a separate temporary database
and do not create example accounts in your local database.

## 2. Project layout

```text
config/
  settings.py             Environment-based database, auth, and security settings
  urls.py                 Authentication, admin, health, and task routes
  wsgi.py / asgi.py        Server entry points
tasks/
  models.py               Task model and status choices
  forms.py                Explicit user-editable fields (never owner)
  views.py                Authenticated and owner-scoped CRUD
  urls.py                 Task URL names
  admin.py                Staff administration
  tests.py                Behavior tests
  migrations/             Committed database schema migrations
templates/
  base.html               Shared navigation and messages
  registration/           Signup and login
  tasks/                  List, detail, editor, and deletion confirmation
  includes/               Shared form rendering
static/css/app.css        Responsive styling
manage.py                 Django command-line entry point
requirements.txt         Pinned direct dependencies
.env.example             Local configuration template
.python-version          Render's Python version selection
build.sh                 Dependency install, static collection, deployment checks
render.yaml              Render web service and PostgreSQL Blueprint
```

### Main routes

| Route | Purpose |
| --- | --- |
| `/accounts/signup/` | Create an account |
| `/accounts/login/` | Log in |
| `/accounts/logout/` | Log out using POST |
| `/` | Your paginated task list |
| `/tasks/new/` | Create a task |
| `/tasks/<id>/` | Task details |
| `/tasks/<id>/edit/` | Edit a task |
| `/tasks/<id>/delete/` | GET confirmation; POST deletion |
| `/admin/` | Trusted staff administration |
| `/health/` | GET database health: 200 `{"status":"ok"}` or 503 |

Normal users only see their own tasks, even if they guess another user's ID.
Admin access is intentionally different: authorized staff can manage all tasks.
Deleting a user also deletes that user's tasks. Due dates can be in the past.
Timestamps are shown in UTC.

## 3. Deploy to Render with PostgreSQL

**The included Blueprint provisions paid resources:** a Starter web service and a
Basic 256 MB PostgreSQL database. Review current pricing in Render before applying
it. A paid web service supports pre-deploy migrations and the dashboard Shell;
a paid database avoids the short lifetime of free databases. Nothing is deployed
merely by running this code locally.

### A. Push the project to GitHub

Create an empty GitHub repository, then run these commands in this directory.
Replace the example URL with your own repository URL:

```powershell
git init
git add .
git --no-pager diff --cached --stat
git commit -m "Create Django task manager"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY.git
git push -u origin main
```

Inspect staged files before committing. Do not include `.env`, `.venv`, the local
SQLite database, or generated `staticfiles`. A private repository is supported;
grant Render access only to the repository you want to deploy.

### B. Apply the Blueprint

1. Sign in at <https://dashboard.render.com/>.
2. Open **Blueprints**, select **New Blueprint Instance** (or **New > Blueprint**).
3. Connect your GitHub repository and select its `main` branch.
4. Render detects the root `render.yaml`. Review the web service, database, region,
   and charges, then apply the Blueprint.
5. Wait for the database and web service to finish provisioning.
6. Open the web service's public `https://...onrender.com` URL.

The Blueprint:

- Creates the database and web service in the same region.
- Injects the database's internal connection URL into `DATABASE_URL`.
- Generates a private `DJANGO_SECRET_KEY`.
- Sets `DJANGO_DEBUG=False`.
- Runs `bash build.sh` to install packages, collect CSS, and check deployment settings.
- Runs `python manage.py migrate --no-input` as a **pre-deploy command**. Migration
  failure stops the deployment; migrations are not performed by each Gunicorn worker.
- Starts Gunicorn on Render's assigned `$PORT`.
- Uses `/health/` to check database connectivity.
- Disables public database access through `ipAllowList: []`; the web service
  connects using Render's private network.

Django automatically reads Render's `RENDER_EXTERNAL_HOSTNAME` into the allowed
hosts and trusted HTTPS origins. You do not need to guess the assigned hostname.
The app trusts Render's forwarded HTTPS header only when `RENDER=true`.

### C. Create an administrator

In the paid web service's **Shell** tab:

```bash
python manage.py createsuperuser
```

Enter credentials interactively. Visit `https://YOUR_SERVICE.onrender.com/admin/`.
Do not put admin passwords in source code, the Blueprint, or a build command.
Normal users register on `/accounts/signup/`.

### D. Verify the live deployment

1. Open `/health/`: expect `{"status":"ok"}` with HTTP 200.
2. Open `/accounts/signup/` and check that the page is styled.
3. Register and log in as user A; create, view, edit, and delete a task.
4. Create a second account in a separate browser/private session. Verify that
   it cannot see user A's tasks or open an A-owned task URL.
5. Log out and verify that `/` redirects to login.
6. Create a task, redeploy, and verify it remains in PostgreSQL.
7. Check Render logs for application errors and run `python manage.py check --deploy`
   in the service Shell.

Example public health check from PowerShell:

```powershell
Invoke-RestMethod https://YOUR_SERVICE.onrender.com/health/
```

Live deployment and PostgreSQL connectivity must be checked in your Render account;
local SQLite tests do not prove the remote deployment is healthy.

### E. Subsequent changes

After changing models, generate and commit migrations locally:

```powershell
.\.venv\Scripts\python.exe manage.py makemigrations tasks
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py test tasks
```

Commit and push the code **and migration files**. Render redeploys on pushes to the
linked branch. Use backward-compatible schema changes: the old application may
continue serving requests while pre-deploy migrations run.

Code rollback does not undo database migrations. Back up the database before
destructive schema changes and verify that backups can actually be restored.

## 4. Manual Render deployment (alternative to the Blueprint)

Do not do this as well as applying the Blueprint; choose one deployment method.

1. Create a paid PostgreSQL database and paid Python web service in the same region.
2. Connect the service to your GitHub repository.
3. Configure:

| Setting | Value |
| --- | --- |
| Build command | `bash build.sh` |
| Pre-deploy command | `python manage.py migrate --no-input` |
| Start command | `python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --access-logfile - --error-logfile -` |
| Health check path | `/health/` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | Generate a strong random secret in Render |
| `DATABASE_URL` | Database **internal** connection URL |

The root `.python-version` selects Python 3.12. Restrict the database's external
access in its settings. Follow the same admin creation and verification steps.

### Free demo option

Render's free web service is suitable for a demo, not production: it sleeps after
15 minutes of inactivity, has cold starts, and has an ephemeral filesystem.
Free PostgreSQL expires after 30 days according to Render's current documentation.
Do not use a free database for data you need to retain.

For a temporary free demo, create resources manually, omit the pre-deploy command,
and use this build command to migrate after the regular build:

```bash
bash build.sh && python manage.py migrate --no-input
```

Keep the other environment variables and start command as above, and use
PostgreSQL, never SQLite. This build-time migration workaround lacks the paid
pre-deploy phase; it is not the recommended production setup. A free web service
does not provide the Shell used above for creating an admin; normal signup still
works. Check current free-tier limits before choosing this option.

## 5. Environment and production operations

| Variable | Use |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required everywhere; generated once and kept private |
| `DJANGO_DEBUG` | `True` locally only; defaults to `False` |
| `DATABASE_URL` | Optional locally; required PostgreSQL URL in production |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated exact hostnames, without schemes |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins including `https://` |
| `RENDER_EXTERNAL_HOSTNAME` | Provided by Render; automatically allowed |
| `RENDER` | Provided by Render; enables its trusted proxy HTTPS header |

Production refuses to start without a secret, allowed host, or PostgreSQL URL.
HTTPS redirects, secure session/CSRF cookies, and one-year HSTS are enabled with
debug off. HSTS includes subdomains and the preload directive: only attach a
custom domain after confirming its subdomains can all operate over HTTPS.

For a custom domain, first add it in Render and configure DNS/TLS. Then add its
hostname to `DJANGO_ALLOWED_HOSTS` and its HTTPS URL to
`DJANGO_CSRF_TRUSTED_ORIGINS`, retaining any existing entries, and redeploy.
Never use `*` for allowed hosts or turn on production debug to work around errors.

Render's filesystem is ephemeral. PostgreSQL stores all persistent application
data; there are no file uploads. If you later add uploads, use durable object
storage instead of writing to the web service's local filesystem.

This is a functional starter, not a complete operational security program.
Before a public business launch:

- Add login/signup/admin rate limiting using a maintained Django integration or
  a correctly configured edge service. Django authentication alone does not
  throttle brute-force requests.
- Add password recovery and email verification with a real email provider if
  your users require them. This starter does not send email or reset passwords.
- Configure uptime/error alerts, database backups and restore drills.
- Keep Python and dependencies patched; review permissions and staff access.
- Keep `DJANGO_SECRET_KEY` stable across deploys; rotate it deliberately if exposed.
- Review privacy/retention requirements for stored user data.

### Troubleshooting

| Symptom | Resolution |
| --- | --- |
| Missing-secret startup error | Generate/set `DJANGO_SECRET_KEY`; do not leave the example blank |
| Database connection or SSL error | Verify the internal PostgreSQL URL, same region, database status, and Render logs |
| HTTP 400 / `DisallowedHost` | Set the exact hostname in `DJANGO_ALLOWED_HOSTS` |
| CSRF 403 after adding a custom domain | Set its full HTTPS origin and confirm proxy/TLS configuration |
| CSS missing or manifest error | Ensure `collectstatic` succeeded and the static file is committed; redeploy |
| Missing tables | Check pre-deploy migration logs and committed migration files |
| Redirect loop outside Render | Configure a trusted TLS proxy appropriately; never trust arbitrary client forwarding headers |
| `/health/` returns 503 | Database connectivity failed; investigate server logs and database availability |

## References

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Render Django deployment](https://render.com/docs/deploy-django)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render pre-deploy commands](https://render.com/docs/deploys#pre-deploy-command)
- [Render Python versions](https://render.com/docs/python-version)
- [Render free-tier limitations](https://render.com/docs/free)
