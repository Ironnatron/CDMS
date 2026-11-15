# Django task manager

A complete server-rendered Django application with user authentication and private
task CRUD. Uses Django 5.2 LTS, SQLite locally, PostgreSQL on Render, and WhiteNoise
for production CSS. No frontend build tools or third-party CDN assets are needed.

**Clinical document functionality is a synthetic-data prototype only. Never
upload real patient information, clinical data, or sensitive identifiers.** The
application is not validated for HIPAA, GDPR, or other clinical requirements.

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
- Optional synthetic-document uploads and shared organization roles, disabled by default.

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

### Synthetic document prototype

The prototype has **one shared organization**. All users assigned any document
role can see and download **every** document; there are no per-document permissions
or separate organizations. User registration does not grant document access.

| Document role | Permissions |
| --- | --- |
| Superadmin | Read, upload, download, delete, and assign or remove roles |
| Administrator | Read, upload, download, and delete documents |
| Clinician | Read, download, and upload documents |
| Viewer | Read and download documents |
| No role | No document access, even if the user has a task account |

There is **at most one** document superadmin, enforced by a database constraint.
Before the one-time setup there is none. Only the superadmin can manage other
users' document roles. The superadmin cannot remove or downgrade their own role
through the interface, and there is no superadmin transfer UI. Database access or
Django administrative access is still privileged and must be restricted.
Existing administrator roles remain intact after migration, but they no longer
grant role-management access. A Django superuser or staff account does not
automatically receive a document role. Tasks remain private to their owners and
use their existing permissions. Uploaded documents must be deleted before the
uploader's user account can be deleted.

After setup, select **Admin sign in** or visit `/documents/admin-login/`. Use your
existing account credentials: a document superadmin goes directly to role
management, and a document administrator goes to the shared document list.
Clinicians, viewers, and users without a document role use the regular login.
This is a separate sign-in page, not a separate set of accounts; authorization
is still checked for every document request.

**Enable locally and initialize the document superadmin:**

1. Apply migrations with `.\.venv\Scripts\python.exe manage.py migrate`, then
   create an ordinary account at `/accounts/signup/`. Use a fictional username.
2. Generate a unique, random setup secret locally:

   ```powershell
   .\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_urlsafe(64))"
   ```

3. In your existing `.env`, set `SYNTHETIC_DOCUMENTS_ENABLED=True` and set
   `DOCUMENT_SUPERADMIN_SETUP_TOKEN` to the generated secret. Do not commit or
   share it. The setup checks its length (43–256 characters), but length alone
   does not establish randomness; use the generator above.
4. Restart `runserver`, log in as the account that should become the superadmin,
   and select **Set up documents** or visit `/documents/setup/`. Check the
   username displayed, then enter the setup secret.
5. After setup succeeds, remove `DOCUMENT_SUPERADMIN_SETUP_TOKEN` from `.env` and
   restart the server. In **Documents > Manage roles**, the superadmin can assign
   active accounts the clinician, viewer, or administrator role. Access changes
   take effect on the next request.
6. Upload a fictional `.pdf` or `.txt` file, up to 5 MB. No file content is
   inspected or scanned; file extensions do not prove a file is safe.

The setup secret is required only for the first setup; any signed-in user who
possesses it can claim that role until setup completes. Keep it private, and do
not leave the setup window open unattended. Setup is recorded in the database
and cannot be repeated through the interface even if the token remains set.
Protect access to the superadmin account: no role-transfer or account-recovery
workflow is included.

Set `SYNTHETIC_DOCUMENTS_ENABLED=False` and restart to disable **all** document
routes. This does not erase existing files or database entries. Files are stored
outside the static folder in ignored `private_documents/` and are available only
through authenticated role-checked downloads in the app. They are not encrypted
by the application; access to the machine or its storage can bypass the app.

### Optional Render demo setup

Deploy the latest code and migrations first. **Render's free filesystem is
ephemeral**: uploaded files may disappear on restart, spin-down, or redeploy while
their database records remain. Missing-file downloads show an error; an
administrator can delete the stale record. Do not rely on this as a backup.

1. Push the code and migration to GitHub and wait for Render to deploy them.
2. Generate a setup secret on your computer using the command in the local setup
   section above. Copy it privately; do not commit it or use Render's shorter
   automatic secret generator.
3. Under the web service's **Environment**, set `SYNTHETIC_DOCUMENTS_ENABLED` to
   `True` and `DOCUMENT_SUPERADMIN_SETUP_TOKEN` to the generated secret. Choose
   **Save, rebuild, and deploy**. Never enable this for real clinical data.
4. Register or log in as the intended fictional superadmin account. Open
   `/documents/setup/`, verify the displayed username, and submit the secret.
   The free Render service does not need Shell or public PostgreSQL access for
   this flow.
5. Immediately remove `DOCUMENT_SUPERADMIN_SETUP_TOKEN` in Render's **Environment**
   and choose **Save and deploy**. A redeploy can clear any temporary files.
   The database remembers setup is complete. Log in and use **Documents >
   Manage roles** to grant other accounts access.

This prototype lacks, among other things, clinical-grade security review, audit
logging, malware scanning, durable encrypted document storage, backups, email
verification, password recovery, MFA, and production access governance. It must
not be used for real patient data, even if enabled on a public Render service.

### Tests

After configuring `.env`:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
.\.venv\Scripts\python.exe manage.py test tasks documents
```

The tests cover signup/password validation, login/logout, safe redirects, private
task access, CRUD, validation, optional dates, pagination, escaped user content,
CSRF rejection, health-check failures, document role enforcement, file validation,
and synthetic document operations. Tests use a separate temporary database and
temporary files; they do not create example accounts in your local database.

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
documents/
  models.py               Shared synthetic documents and per-user document roles
  forms.py / views.py     Upload validation and role-checked operations
  tests.py / migrations/  Prototype tests and database migrations
templates/
  base.html               Shared navigation and messages
  registration/           Signup and login
  tasks/                  List, detail, editor, and deletion confirmation
  documents/              Synthetic-document and role management pages
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
| `/documents/` | Shared synthetic documents, when enabled and role-authorized |
| `/documents/new/` | Synthetic file upload for clinicians, administrators, and superadmin |
| `/documents/<id>/download/` | Role-checked attachment download |
| `/documents/<id>/delete/` | Administrator-only confirmation and deletion |
| `/documents/setup/` | One-time, secret-protected superadmin setup |
| `/documents/admin-login/` | Separate sign-in for document administrators and superadmin |
| `/documents/roles/` | Superadmin-only role management |
| `/admin/` | Trusted staff administration |
| `/health/` | GET database health: 200 `{"status":"ok"}` or 503 |

Normal users only see their own tasks, even if they guess another user's ID.
Admin access is intentionally different: authorized staff can manage all tasks.
Deleting a user also deletes that user's tasks. Due dates can be in the past.
Timestamps are shown in UTC.

## 3. Deploy to Render with PostgreSQL

**The included Blueprint selects a free web service and free Render PostgreSQL.**
It is for demos, not production. Render's free database **expires after 30 days**,
then becomes inaccessible; Render deletes it and its data after a 14-day grace
period unless it is upgraded. The free database has no managed backups. Export
any data you need before expiry; an export requires separately enabling and
restricting external database access, since the Blueprint disables it by default.
See [Render's free-tier limits](https://render.com/docs/free) for current details.

The free web service sleeps after 15 minutes without inbound traffic and may take
about a minute to wake up. It has an ephemeral filesystem and no Render Shell.
Free usage has monthly limits, and overages can be billed if a payment method is
present; review your Render billing and usage settings. Render permits only one
active free Postgres database per workspace. If Render still requests payment or
verification after both plans show **Free**, check its on-screen requirements or
contact Render support; this project cannot bypass account requirements.

### A. Push the project to GitHub

If you already connected and pushed this project to GitHub, commit and push the
updated Blueprint first:

```powershell
git add render.yaml README.md
git --no-pager diff --cached
git commit -m "Configure free Render deployment"
git push origin main
```

For a new project instead, create an **empty** GitHub repository, then run these
commands in this directory. Replace the example URL with your repository URL:

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

Generate a strong, unique secret locally:

```powershell
python -c "import secrets; print(secrets.token_urlsafe(64))"
```

Copy the result privately. Do not commit it, share it, or paste it into logs.
Render's automatic 256-bit Blueprint secret is only 44 characters when encoded,
so it does not meet Django's 50-character deployment check. This Blueprint
therefore prompts for a longer secret instead.

1. Sign in at <https://dashboard.render.com/>.
2. Open **Blueprints**, select **New Blueprint Instance** (or **New > Blueprint**).
3. Connect your GitHub repository and select its `main` branch.
4. Render detects the root `render.yaml`. **Confirm both the web service and
   database say Free and the estimated charges are zero before applying.**
   If the dashboard still shows paid plans, make sure your latest commit is pushed
   and Render is using the correct repository and branch.
5. When prompted for `DJANGO_SECRET_KEY`, paste the generated secret.
6. Wait for the database and web service to finish provisioning.
7. Open the web service's public `https://...onrender.com` URL.

For an **existing** Blueprint, Render does not prompt again for `sync: false`
variables. Open the web service's **Environment** page, replace
`DJANGO_SECRET_KEY` with the generated secret, and select **Save, rebuild, and
deploy**. Changing an existing key invalidates sessions and other Django-signed
data. Keep the new key stable on future deploys; never regenerate it in a build.

If you already created paid resources, pushing this file alone does not guarantee
they have been downgraded or stopped. Review their plans and charges in the
dashboard and handle any paid resources separately. Do not delete a database that
contains data you need.

The Blueprint:

- Creates a free database and a free web service in the same region.
- Injects the database's internal connection URL into `DATABASE_URL`.
- Prompts for a private `DJANGO_SECRET_KEY` on initial Blueprint creation.
- Sets `DJANGO_DEBUG=False`.
- Runs `bash build.sh` to install packages, collect CSS, and check deployment settings,
  then runs `python manage.py migrate --no-input` during the build. The free plan
  does not support a pre-deploy command. A migration failure fails the build.
- Starts Gunicorn on Render's assigned `$PORT`.
- Uses `/health/` to check database connectivity.
- Disables public database access through `ipAllowList: []`; the web service
  connects using Render's private network.

Django automatically reads Render's `RENDER_EXTERNAL_HOSTNAME` into the allowed
hosts and trusted HTTPS origins. You do not need to guess the assigned hostname.
The app trusts Render's forwarded HTTPS header only when `RENDER=true`.

### C. Create a normal account

Visit `https://YOUR_SERVICE.onrender.com/accounts/signup/`, create an account,
and log in. The free web service does not provide Render Shell access, so the
interactive `createsuperuser` command cannot be run there. Normal task management
does not require a Django admin account. Do not put admin passwords in source
code, environment examples, or build commands.

### D. Verify the live deployment

1. Open `/health/`: expect `{"status":"ok"}` with HTTP 200.
2. Open `/accounts/signup/` and check that the page is styled.
3. Register and log in as user A; create, view, edit, and delete a task.
4. Create a second account in a separate browser/private session. Verify that
   it cannot see user A's tasks or open an A-owned task URL.
5. Log out and verify that `/` redirects to login.
6. Create a task, redeploy, and verify it remains in PostgreSQL.
7. Check Render build and application logs for errors. The build already runs
   `python manage.py check --deploy`.

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
continue serving requests while build-time migrations run. Migrations modify the
live database even if a later deployment step fails.

Code rollback does not undo database migrations. Free Render Postgres has no
managed backups; export data you need and verify you can restore it before making
destructive changes.

## 4. Manual Render deployment (alternative to the Blueprint)

Do not do this as well as applying the Blueprint; choose one deployment method.

1. Create a **free** PostgreSQL database and a **free** Python web service in the
   same region, and verify charges before confirming.
2. Connect the service to your GitHub repository.
3. Configure:

| Setting | Value |
| --- | --- |
| Build command | `bash build.sh && python manage.py migrate --no-input` |
| Pre-deploy command | Leave empty; unavailable on the free web plan |
| Start command | `python -m gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 1 --access-logfile - --error-logfile -` |
| Health check path | `/health/` |
| `DJANGO_DEBUG` | `False` |
| `DJANGO_SECRET_KEY` | Generate the long random secret as described above and paste it into Render |
| `DATABASE_URL` | Database **internal** connection URL |

The root `.python-version` selects Python 3.12. Disable the database's external
access in its settings unless you need it for a controlled export. Follow the
normal signup and verification steps above.

### Longer-lived free database option

If you need to keep data beyond 30 days without paying for Render PostgreSQL,
[Neon's free PostgreSQL plan](https://neon.com/pricing) is a possible alternative,
subject to its own usage limits and terms. Create a free Neon project, then deploy
the Render **web service manually** as described above, using Neon's PostgreSQL
connection string for `DATABASE_URL` instead of creating a Render database.
Keep the connection string secret and confirm TLS is enabled. Do not apply the
included Blueprint for this alternative: it creates a separate Render database.
Neon is a separate provider and will receive your application data. Switching
an existing app to a new database does not automatically transfer its data.

## 5. Environment and production operations

| Variable | Use |
| --- | --- |
| `DJANGO_SECRET_KEY` | Required everywhere; generated once and kept private |
| `DJANGO_DEBUG` | `True` locally only; defaults to `False` |
| `DATABASE_URL` | Optional locally; required PostgreSQL URL in production |
| `SYNTHETIC_DOCUMENTS_ENABLED` | Explicit opt-in; defaults to `False`. Synthetic data only |
| `DOCUMENT_SUPERADMIN_SETUP_TOKEN` | One-time setup secret; remove after setup |
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

Render's filesystem is ephemeral. PostgreSQL stores account, task, document
metadata, and role records; optional synthetic document files are temporary and
may disappear independently. Durable, approved object storage and a full security
review are required before considering any real clinical data.

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
| Missing-secret startup error or `security.W009` | Generate a long random `DJANGO_SECRET_KEY` as above, set it in the web service's Environment, and rebuild |
| Database connection or SSL error | Verify the database URL, provider status, TLS, and Render logs; use the internal URL for Render PostgreSQL |
| HTTP 400 / `DisallowedHost` | Set the exact hostname in `DJANGO_ALLOWED_HOSTS` |
| CSRF 403 after adding a custom domain | Set its full HTTPS origin and confirm proxy/TLS configuration |
| CSS missing or manifest error | Ensure `collectstatic` succeeded and the static file is committed; redeploy |
| Missing tables | Check build-time migration logs and committed migration files |
| Redirect loop outside Render | Configure a trusted TLS proxy appropriately; never trust arbitrary client forwarding headers |
| `/health/` returns 503 | Database connectivity failed; investigate server logs and database availability |

## References

- [Django deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/)
- [Render Django deployment](https://render.com/docs/deploy-django)
- [Render Blueprint specification](https://render.com/docs/blueprint-spec)
- [Render pre-deploy commands](https://render.com/docs/deploys#pre-deploy-command)
- [Render Python versions](https://render.com/docs/python-version)
- [Render free-tier limitations](https://render.com/docs/free)
