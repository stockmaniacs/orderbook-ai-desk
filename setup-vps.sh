#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# setup-vps.sh — One-time setup for the Orderbook AI Desk backend on Oracle VPS
#
# Run ONCE on the VPS after cloning the repo:
#   bash setup-vps.sh
#
# Prerequisites already on the server:
#   Nginx, PM2, Node.js 22, PostgreSQL, Redis
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

PROJECT_DIR="/home/ubuntu/projects/orderbook-ai-desk"
BACKEND_DIR="$PROJECT_DIR/backend"
LOG_DIR="/home/ubuntu/logs"
DB_NAME="orderbook_prod"
NGINX_CONF="/etc/nginx/sites-available/orderbook-api"

echo "======================================================"
echo "  Orderbook AI Desk — VPS Setup"
echo "======================================================"

# ── 1. System packages ────────────────────────────────────────────────────────
echo ""
echo "→ Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.11 \
    python3.11-venv \
    python3.11-dev \
    python3-pip \
    build-essential \
    libpq-dev \
    certbot \
    python3-certbot-nginx \
    postgresql-client

# ── 2. pgvector extension ─────────────────────────────────────────────────────
echo ""
echo "→ Installing pgvector..."
PG_VERSION=$(psql --version | grep -oP '\d+' | head -1)
sudo apt-get install -y -qq "postgresql-$PG_VERSION-pgvector" || {
    echo "  pgvector package not found via apt, building from source..."
    sudo apt-get install -y -qq postgresql-server-dev-$PG_VERSION
    git clone --branch v0.7.4 https://github.com/pgvector/pgvector.git /tmp/pgvector
    cd /tmp/pgvector && make && sudo make install && cd -
    rm -rf /tmp/pgvector
}

# ── 3. Log directory ──────────────────────────────────────────────────────────
echo ""
echo "→ Creating log directory at $LOG_DIR..."
mkdir -p "$LOG_DIR"

# ── 4. PostgreSQL database ────────────────────────────────────────────────────
echo ""
echo "→ Setting up PostgreSQL database..."
sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname = '$DB_NAME'" | grep -q 1 || \
    sudo -u postgres createdb "$DB_NAME"
sudo -u postgres psql -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS vector;" 2>/dev/null || true
echo "  Database '$DB_NAME' ready."

# ── 5. Python virtual environment ─────────────────────────────────────────────
echo ""
echo "→ Creating Python virtual environment..."
python3.11 -m venv "$BACKEND_DIR/venv"
source "$BACKEND_DIR/venv/bin/activate"
pip install --quiet --upgrade pip
pip install --quiet -r "$BACKEND_DIR/requirements.txt"
echo "  Python venv ready at $BACKEND_DIR/venv"

# ── 6. .env file ─────────────────────────────────────────────────────────────
echo ""
if [ ! -f "$BACKEND_DIR/.env" ]; then
    echo "→ Creating .env from template..."
    DB_USER=$(sudo -u postgres psql -tAc "SELECT current_user")
    cat > "$BACKEND_DIR/.env" <<EOF
DATABASE_URL=postgresql+asyncpg://$DB_USER@localhost/$DB_NAME
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
SECRET_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
ALLOWED_ORIGINS=https://YOUR_FRONTEND_DOMAIN
DEBUG=false
EOF
    echo "  .env created. EDIT IT NOW to set ALLOWED_ORIGINS to your Cloudflare Pages domain."
else
    echo "→ .env already exists — skipping."
fi

# ── 7. Alembic migrations ─────────────────────────────────────────────────────
echo ""
echo "→ Running database migrations..."
cd "$BACKEND_DIR"
source venv/bin/activate
alembic upgrade head
cd -

# ── 8. PM2 setup ─────────────────────────────────────────────────────────────
echo ""
echo "→ Starting services with PM2..."
pm2 start "$PROJECT_DIR/ecosystem.config.js"
pm2 save
pm2 startup systemd -u ubuntu --hp /home/ubuntu | tail -1 | bash || true
echo "  PM2 processes started and saved."

# ── 9. Nginx config ──────────────────────────────────────────────────────────
echo ""
echo "→ Installing Nginx config..."
sudo cp "$PROJECT_DIR/deploy/nginx-backend.conf" "$NGINX_CONF"
sudo ln -sf "$NGINX_CONF" /etc/nginx/sites-enabled/orderbook-api 2>/dev/null || true
sudo nginx -t && sudo systemctl reload nginx
echo "  Nginx config installed."
echo ""
echo "  ⚠  Edit $NGINX_CONF and replace YOUR_BACKEND_DOMAIN with your real domain."
echo "  Then run: sudo certbot --nginx -d YOUR_BACKEND_DOMAIN"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  Setup complete!"
echo ""
echo "  Next steps:"
echo "  1. Edit $BACKEND_DIR/.env  →  set ALLOWED_ORIGINS"
echo "  2. Edit $NGINX_CONF        →  set YOUR_BACKEND_DOMAIN"
echo "  3. sudo certbot --nginx -d YOUR_BACKEND_DOMAIN"
echo "  4. pm2 logs orderbook-api  →  verify API is running"
echo "  5. curl http://localhost:8000/health"
echo "======================================================"
