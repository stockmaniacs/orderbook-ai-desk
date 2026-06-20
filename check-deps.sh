#!/usr/bin/env bash
# check-deps.sh — Run on the VPS to verify all dependencies are present
# Usage: bash check-deps.sh
set -euo pipefail

PASS="✓"
FAIL="✗"
WARN="⚠"

ok()   { echo "  $PASS  $1"; }
fail() { echo "  $FAIL  $1"; MISSING=1; }
warn() { echo "  $WARN  $1"; }

MISSING=0

echo ""
echo "════════════════════════════════════════"
echo "  Orderbook AI Desk — Dependency Check"
echo "════════════════════════════════════════"

# Python 3.11
echo ""
echo "── Python ──"
if python3.11 --version &>/dev/null; then
    ok "Python 3.11: $(python3.11 --version)"
else
    fail "Python 3.11 not found → sudo apt install python3.11 python3.11-venv python3.11-dev"
fi

if python3.11 -m venv --help &>/dev/null; then
    ok "python3.11-venv available"
else
    fail "python3.11-venv missing → sudo apt install python3.11-venv"
fi

# PostgreSQL
echo ""
echo "── PostgreSQL ──"
if pg_isready &>/dev/null; then
    ok "PostgreSQL running: $(psql --version)"
else
    fail "PostgreSQL not running or not installed"
fi

# pgvector
echo ""
echo "── pgvector ──"
if sudo -u postgres psql -c "CREATE EXTENSION IF NOT EXISTS vector;" orderbook_prod &>/dev/null 2>&1; then
    ok "pgvector extension available"
    sudo -u postgres psql -c "DROP EXTENSION IF EXISTS vector;" orderbook_prod &>/dev/null 2>&1 || true
else
    PG_VER=$(pg_config --version | grep -oP '\d+' | head -1)
    if apt-cache show "postgresql-$PG_VER-pgvector" &>/dev/null 2>&1; then
        fail "pgvector not installed → sudo apt install postgresql-$PG_VER-pgvector"
    else
        warn "pgvector not in apt — needs build from source (setup-vps.sh handles this)"
    fi
fi

# Redis
echo ""
echo "── Redis ──"
if redis-cli ping &>/dev/null; then
    ok "Redis running: $(redis-server --version | head -1)"
else
    fail "Redis not running → sudo systemctl start redis"
fi

# Nginx
echo ""
echo "── Nginx ──"
if nginx -v &>/dev/null 2>&1; then
    ok "Nginx: $(nginx -v 2>&1)"
else
    fail "Nginx not found → sudo apt install nginx"
fi

# Certbot
echo ""
echo "── Certbot ──"
if certbot --version &>/dev/null 2>&1; then
    ok "Certbot: $(certbot --version)"
else
    warn "Certbot not found → sudo apt install certbot python3-certbot-nginx"
fi

# PM2
echo ""
echo "── PM2 ──"
if pm2 --version &>/dev/null; then
    ok "PM2: $(pm2 --version)"
else
    fail "PM2 not found → npm install -g pm2"
fi

# Node.js
echo ""
echo "── Node.js ──"
if node --version &>/dev/null; then
    ok "Node.js: $(node --version)"
else
    fail "Node.js not found"
fi

# libpq-dev (needed for psycopg2-binary build)
echo ""
echo "── System libs ──"
if dpkg -l libpq-dev &>/dev/null 2>&1; then
    ok "libpq-dev installed"
else
    warn "libpq-dev missing → sudo apt install libpq-dev (needed for psycopg2)"
fi

if dpkg -l build-essential &>/dev/null 2>&1; then
    ok "build-essential installed"
else
    warn "build-essential missing → sudo apt install build-essential"
fi

# Repo
echo ""
echo "── Project ──"
if [ -d "/home/ubuntu/projects/orderbook-ai-desk" ]; then
    ok "Repo cloned at /home/ubuntu/projects/orderbook-ai-desk"
else
    warn "Repo not cloned yet — run setup-vps.sh after cloning"
fi

if [ -f "/home/ubuntu/projects/orderbook-ai-desk/backend/venv/bin/uvicorn" ]; then
    ok "Python venv exists with uvicorn"
else
    warn "Python venv not set up yet — setup-vps.sh will create it"
fi

if [ -f "/home/ubuntu/projects/orderbook-ai-desk/backend/.env" ]; then
    ok ".env file present"
else
    warn ".env not created yet — setup-vps.sh will create it from template"
fi

# Summary
echo ""
echo "════════════════════════════════════════"
if [ "$MISSING" -eq 0 ]; then
    echo "  All required dependencies found!"
    echo "  Run: bash setup-vps.sh"
else
    echo "  Some dependencies are missing."
    echo "  Fix the items marked ✗ above, then run: bash setup-vps.sh"
fi
echo "════════════════════════════════════════"
echo ""
