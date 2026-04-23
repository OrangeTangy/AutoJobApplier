# AutoJobApplier

A self-hosted job application assistant. Discovers jobs from your email or by URL, matches each one to your best resume automatically, and handles Playwright-based form submission — with a mandatory human approval gate before anything is ever sent.

**No AI API key required.** Resume matching and job parsing use local TF-IDF similarity and regex — completely free to run. **No Docker, no terminal, no localhost URLs to remember.** Just download the release, double-click, and use it.

---

## Download and run

Grab the latest release for your OS from the **[Releases page](../../releases/latest)** and extract it.

| OS | File | How to run |
|---|---|---|
| Windows | `AutoJobApplier-windows.zip` | Unzip, then double-click **`AutoJobApplier.exe`** |
| macOS | `AutoJobApplier-macos.zip` | Unzip, then double-click **`AutoJobApplier`** (first launch may require right-click → Open) |
| Linux | `AutoJobApplier-linux.tar.gz` | `tar -xzf … && ./AutoJobApplier-linux/AutoJobApplier` |

The app starts an embedded server, opens your browser to the UI, and shows a system-tray icon. Close from the tray to quit.

### First launch
On first run the app downloads a Chromium build (~180 MB, one-time) so Playwright can fill out forms. Everything else is bundled.

### Your data lives at
- **Windows:** `%LOCALAPPDATA%\AutoJobApplier\`
- **macOS:** `~/Library/Application Support/AutoJobApplier/`
- **Linux:** `~/.local/share/AutoJobApplier/`

That directory holds the SQLite database, uploaded resumes, screenshots, logs, and the Chromium install. Delete it to fully reset the app.

---

## First-time setup (inside the app)

1. **Register** an account when the app opens
2. **Profile** → fill in work authorization, salary range, relocation preferences, work history
3. **Resumes** → drag in one or more `.tex` files (one per specialisation)
4. **Jobs** → paste a job URL, or go to Ingestion to import from Handshake / email

The system auto-picks the best-matching resume for each job.

---

## How it works

```
Job URL / Email / CSV
        ↓
  Fetch + parse (regex, no API key needed)
        ↓
  Fit score vs your profile (keyword overlap)
        ↓
  Best resume selected from your library (TF-IDF)
        ↓
  Questionnaire filled from profile fields
        ↓
  ┌─────────────────────────────────┐
  │   YOU REVIEW AND APPROVE        │  ← mandatory human gate
  └─────────────────────────────────┘
        ↓
  Playwright submits form (Workday / Greenhouse / Lever / Ashby / Generic)
        ↓
  Screenshot saved, audit log written
```

### Safety guarantees (hard-coded, not configurable)
- **Never submits without your explicit approval** — one click per application
- **Pauses on any CAPTCHA, MFA, or OTP** — does not attempt to bypass
- **Respects robots.txt** — checked before any browser navigation
- **Never fabricates** — questionnaire answers pulled directly from your profile
- **Full audit log** — every action written to the local database

---

## Resume library

Drop multiple `.tex` files in at **Resumes → Add Resume** and label each by focus area:

| Label | Use case |
|---|---|
| `Backend — Python/AWS` | Python backend roles |
| `Data Scientist — ML/PyTorch` | ML/data science roles |
| `Full-Stack — React/Node` | Full-stack web roles |

For each job, TF-IDF cosine similarity ranks every resume against the job description and auto-selects the best match. You can always swap it on the review screen before approving.

---

## Job ingestion

| Method | Where |
|---|---|
| URL paste | Jobs page → paste any job posting URL |
| Handshake CSV | Ingestion → Handshake CSV tab |
| URL list | Ingestion → URL List tab (one per line) |
| JSON array | Ingestion → JSON Import tab |
| Email (IMAP) | Ingestion → Email Sources (hourly polling, in-process) |
| Email (Gmail) | Ingestion → Email Sources (OAuth) |

Email polling runs in the background every hour while the app is open.

---

## Architecture (desktop mode)

```
┌─────────────────────────────────────────────┐
│            AutoJobApplier.exe               │
├─────────────────────────────────────────────┤
│   ┌──────────────┐    ┌──────────────┐     │
│   │   Next.js    │◀──▶│   FastAPI    │     │
│   │   (static)   │    │   (uvicorn)  │     │
│   └──────────────┘    └──────┬───────┘     │
│                              │              │
│   ┌──────────────┐    ┌──────▼───────┐     │
│   │    SQLite    │◀───│  Thread-pool │     │
│   │  (aiosqlite) │    │  + scheduler │     │
│   └──────────────┘    └──────────────┘     │
│   ┌──────────────────────────────────┐     │
│   │ Playwright (Chromium, on-demand) │     │
│   └──────────────────────────────────┘     │
└─────────────────────────────────────────────┘
```

**Backend:** Python 3.11, FastAPI, SQLAlchemy 2.0 async, Alembic
**Queue:** In-process `ThreadPoolExecutor` + lightweight scheduler (no Redis/Celery)
**Frontend:** Next.js 15 static export, TypeScript, React Query v5, Tailwind CSS
**Submission:** Playwright/Chromium — adapters for Workday, Greenhouse, Lever, Ashby, Generic
**Matching:** scikit-learn TF-IDF cosine similarity
**Encryption:** Fernet (AES-128-CBC + HMAC) for sensitive DB columns
**Auth:** JWT HS256 access + refresh tokens

---

## Build from source

You only need this if you want to modify the app. Otherwise just download the release.

```bash
# Backend
cd backend
python3.11 -m venv .venv
source .venv/bin/activate            # or .venv\Scripts\activate on Windows
pip install -r requirements.txt
playwright install chromium

# Frontend (static export)
cd ../frontend
npm ci
npm run build

# Run the launcher
cd ../backend
python launcher.py
```

To build a distributable bundle locally:

```bash
cd backend
pip install pyinstaller
pyinstaller autojobapplier.spec --noconfirm --clean
# Output: backend/dist/AutoJobApplier/
```

GitHub Actions builds Windows + macOS + Linux on every tagged push — see `.github/workflows/release.yml`. Tag a commit `vX.Y.Z` and the three installers publish to a GitHub Release automatically.

---

## Server mode (Docker, optional)

If you want a multi-user Postgres/Redis deployment instead of a single-user desktop app, the original Docker Compose stack is still available — see `docker-compose.yml` and `docker-compose.prod.yml`. Uncomment the Postgres/Redis/Celery lines in `backend/requirements.txt` before building.

---

## License

MIT
