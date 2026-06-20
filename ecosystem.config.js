// PM2 ecosystem config — manages API server, Celery worker, and Celery Beat
// Usage:
//   pm2 start ecosystem.config.js        # start all
//   pm2 reload ecosystem.config.js       # zero-downtime reload (deploy)
//   pm2 stop ecosystem.config.js         # stop all
//   pm2 logs orderbook-api               # tail logs

const BASE = '/home/ubuntu/projects/orderbook-ai-desk/backend';
const VENV = `${BASE}/venv/bin`;

module.exports = {
  apps: [
    {
      name: 'orderbook-api',
      script: `${VENV}/uvicorn`,
      args: 'main:app --host 127.0.0.1 --port 8000 --workers 2',
      cwd: BASE,
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '500M',
      env: {
        NODE_ENV: 'production',
      },
      error_file: '/home/ubuntu/logs/orderbook-api-error.log',
      out_file: '/home/ubuntu/logs/orderbook-api-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'orderbook-worker',
      script: `${VENV}/celery`,
      args: [
        '-A', 'workers.celery_app',
        'worker',
        '-Q', 'technical_high,technical_normal,default',
        '--loglevel=info',
        '--concurrency=2',
      ].join(' '),
      cwd: BASE,
      interpreter: 'none',
      autorestart: true,
      watch: false,
      max_memory_restart: '400M',
      error_file: '/home/ubuntu/logs/orderbook-worker-error.log',
      out_file: '/home/ubuntu/logs/orderbook-worker-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
    {
      name: 'orderbook-beat',
      script: `${VENV}/celery`,
      args: '-A workers.celery_app beat --loglevel=info',
      cwd: BASE,
      interpreter: 'none',
      autorestart: true,
      watch: false,
      error_file: '/home/ubuntu/logs/orderbook-beat-error.log',
      out_file: '/home/ubuntu/logs/orderbook-beat-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
    },
  ],
};
