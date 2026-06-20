# Orderbook AI Desk

AI-powered investment research platform for NSE/BSE universe. Tracks order books, runs fundamental research, maps subcontract relationships, monitors master tracker signals, and performs full technical analysis (Minervini, Stage Analysis, RS Rating, breakout detection).

---

## Architecture

```
Browser → Cloudflare Pages (Next.js) → Oracle VPS (FastAPI + Celery) → PostgreSQL + Redis
```

| Layer | Technology | Host |
|---|---|---|
| Frontend | Next.js 14 (App Router) | Cloudflare Pages |
| Backend API | FastAPI + uvicorn | Oracle VPS · 161.118.181.181 |
| Task queue | Celery 5 + Redis | Oracle VPS |
| Scheduler | Celery Beat | Oracle VPS |
| Database | PostgreSQL 16 + pgvector | Oracle VPS |
| Cache/broker | Redis | Oracle VPS |
| Reverse proxy | Nginx | Oracle VPS |
| SSL | Certbot (Let's Encrypt) | Oracle VPS |

---

## Repository layout

```
orderbook-ai-desk/
├── backend/
│   ├── main.py                        # FastAPI entry point
│   ├── database.py                    # SQLAlchemy async engine + Base
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── alembic/
│   │   ├── env.py
│   │   └── versions/
│   │       ├── 001_order_tracking.py
│   │       ├── 002_company_research.py
│   │       ├── 003_subcontract_opportunity.py
│   │       ├── 004_master_tracker.py
│   │       └── 005_technical_worker.py
│   └── workers/
│       ├── celery_app.py              # Celery instance (imported by all tasks)
│       ├── order_tracking/            # Order Worker
│       ├── company_research/          # Research + Concall Worker
│       ├── subcontract_opportunity/   # Subcontract Worker
│       ├── master_tracker/            # Master Tracker Worker
│       └── technical_analysis/        # Technical AI Worker
├── frontend/
│   ├── app/
│   │   ├── order-tracking/
│   │   ├── research/
│   │   ├── subcontract/
│   │   ├── tracker/
│   │   └── technical/
│   ├── components/
│   ├── lib/api/
│   └── public/                        # Self-contained HTML dashboards
│       ├── master-tracker-dashboard.html
│       ├── technical-dashboard.html
│       ├── research-dashboard.html
│       └── subcontract-dashboard.html
├── deploy/
│   └── nginx-backend.conf             # Nginx reverse proxy config
├── .github/
│   └── workflows/
│       ├── deploy-backend.yml         # SSH deploy to VPS on push to main
│       └── deploy-frontend.yml        # Build + deploy to Cloudflare Pages
├── ecosystem.config.js                # PM2 process config (API + worker + beat)
├── setup-vps.sh                       # One-time VPS setup script
└── CLAUDE.md                          # This file
```

---

## Workers

| Worker | Module | Celery queue | Schedule |
|---|---|---|---|
| Order Worker | `workers.order_tracking` | `default` | 4 PM Mon–Fri |
| Research Worker | `workers.company_research` | `default` | 6 AM daily |
| Concall Worker | `workers.company_research` | `default` | On demand |
| Subcontract Worker | `workers.subcontract_opportunity` | `default` | Weekly Sat |
| Master Tracker Worker | `workers.master_tracker` | `default` | 6 PM Mon–Fri |
| Technical Worker | `workers.technical_analysis` | `technical_high / technical_normal` | 3:45–5:30 PM Mon–Fri |

---

## API endpoints

| Prefix | Router |
|---|---|
| `/api/v1/orders` | Order tracking |
| `/api/v1/research` | Company research |
| `/api/v1/subcontract` | Subcontract opportunity graph |
| `/api/v1/tracker` | Master tracker dashboard |
| `/api/v1/technical` | Technical AI scanner |
| `/health` | Health check (Nginx probe) |

Swagger UI: `https://YOUR_BACKEND_DOMAIN/docs`

---

## Local development

### Prerequisites
```bash
brew install postgresql@16 redis python@3.11 node
brew services start postgresql@16
brew services start redis
```

### Backend
```bash
cd backend
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env          # edit DATABASE_URL
createdb orderbook_dev
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### Celery (separate terminals)
```bash
# Worker
celery -A workers.celery_app worker -Q technical_high,technical_normal,default -l info

# Beat scheduler
celery -A workers.celery_app beat -l info
```

### Frontend
```bash
cd frontend
npm install
cp .env.example .env.local    # NEXT_PUBLIC_API_URL=http://localhost:8000
npm run dev
```

### URLs
| Service | URL |
|---|---|
| Frontend | http://localhost:3000 |
| API docs | http://localhost:8000/docs |
| Technical dashboard | http://localhost:3000/technical-dashboard.html |
| Master tracker | http://localhost:3000/master-tracker-dashboard.html |

---

## Deployment

### Backend (Oracle VPS)
Push to `main` with changes under `backend/` → GitHub Actions runs `.github/workflows/deploy-backend.yml`:
1. SSH into VPS via `appleboy/ssh-action`
2. `git pull origin main`
3. `pip install -r requirements.txt`
4. `alembic upgrade head`
5. `pm2 reload ecosystem.config.js --update-env`
6. Health check `curl http://localhost:8000/health`

**Required GitHub secret:** `VPS_SSH_KEY` — contents of `~/.ssh/oracle/ssh-key-2026-06-14.key`

### Frontend (Cloudflare Pages)
Push to `main` with changes under `frontend/` → GitHub Actions runs `.github/workflows/deploy-frontend.yml`:
1. `npm ci && npm run build`
2. `cloudflare/pages-action` deploys `.next/` to Cloudflare Pages

**Required GitHub secrets:** `CLOUDFLARE_API_TOKEN`, `CLOUDFLARE_ACCOUNT_ID`
**Required GitHub variable:** `NEXT_PUBLIC_API_URL` (e.g. `https://api.yourdomain.com`)

### One-time VPS setup
```bash
ssh -i ~/.ssh/oracle/ssh-key-2026-06-14.key ubuntu@161.118.181.181
cd /home/ubuntu/projects/orderbook-ai-desk
bash setup-vps.sh
```

See the "One-time server setup" section below for full steps.

---

## One-time server setup (after first git clone on VPS)

```bash
# 1. Clone the repo
mkdir -p /home/ubuntu/projects
cd /home/ubuntu/projects
git clone https://github.com/stockmaniacs/orderbook-ai-desk.git
cd orderbook-ai-desk

# 2. Run setup script
bash setup-vps.sh

# 3. Edit .env
nano backend/.env
# Set: ALLOWED_ORIGINS=https://your-pages-domain.pages.dev

# 4. Edit Nginx config
sudo nano /etc/nginx/sites-available/orderbook-api
# Replace YOUR_BACKEND_DOMAIN with your real domain

# 5. SSL
sudo certbot --nginx -d your-backend-domain.com

# 6. Verify
curl https://your-backend-domain.com/health
pm2 status
```

---

## Database migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Create a new migration
alembic revision --autogenerate -m "description"

# Rollback one step
alembic downgrade -1
```

Migration files live in `backend/alembic/versions/`. Naming convention: `NNN_description.py`.

---

## Environment variables

### backend/.env
```
DATABASE_URL=postgresql+asyncpg://ubuntu@localhost/orderbook_prod
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
SECRET_KEY=<random 64-char hex>
ALLOWED_ORIGINS=https://your-pages-domain.pages.dev,https://your-custom-domain.com
DEBUG=false
```

### frontend/.env.local (local only — never committed)
```
NEXT_PUBLIC_API_URL=http://localhost:8000
```

### Cloudflare Pages variable (set in dashboard or GitHub Actions vars)
```
NEXT_PUBLIC_API_URL=https://your-backend-domain.com
```

---

## PM2 process map

| Process | Command | Port |
|---|---|---|
| `orderbook-api` | uvicorn main:app --workers 2 | 8000 (internal) |
| `orderbook-worker` | celery worker -Q technical_high,technical_normal,default | — |
| `orderbook-beat` | celery beat | — |

Logs: `/home/ubuntu/logs/orderbook-{api,worker,beat}-{out,error}.log`
