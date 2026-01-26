/**
 * PM2 Ecosystem Config para SEI Daemon
 *
 * Uso:
 *   pm2 start ecosystem.config.cjs
 *   pm2 logs sei-daemon
 *   pm2 stop sei-daemon
 *   pm2 restart sei-daemon
 *   pm2 delete sei-daemon
 *
 * Para iniciar automaticamente no boot:
 *   pm2 startup
 *   pm2 save
 */

module.exports = {
  apps: [
    {
      name: 'sei-daemon',
      script: 'npx',
      args: 'tsx start-daemon.ts',
      cwd: __dirname,

      // Ambiente
      env: {
        NODE_ENV: 'production',
        SEI_HEADLESS: 'true',
      },

      // Arquivo .env
      env_file: '.env',

      // Logs
      log_date_format: 'YYYY-MM-DD HH:mm:ss',
      error_file: 'logs/sei-daemon-error.log',
      out_file: 'logs/sei-daemon-out.log',
      merge_logs: true,

      // Restart policy
      autorestart: true,
      max_restarts: 10,
      min_uptime: '30s',
      restart_delay: 10000, // 10 segundos entre restarts

      // Watchdog
      max_memory_restart: '500M',

      // Não usar watch (daemon gerencia próprio estado)
      watch: false,
    },
  ],
};
