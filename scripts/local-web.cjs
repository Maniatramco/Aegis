// Local development server without an extra CLI worker process.
const path = require('node:path');
const http = require('node:http');
const frontend = path.resolve(__dirname, '../frontend');
process.env.AEGIS_IN_PROCESS_WEB = 'true';
const next = require(path.join(frontend, 'node_modules/next'));
const port = Number(process.argv[2] || 3000);
if (!Number.isInteger(port) || port < 1 || port > 65535) {
  throw new Error('Choose a web port between 1 and 65535.');
}
const app = next({ dev: true, dir: frontend, hostname: '127.0.0.1', port });
app.prepare().then(() => {
  const server = http.createServer(app.getRequestHandler());
  server.on('upgrade', app.getUpgradeHandler());
  server.listen(port, '127.0.0.1', () => console.log(`Aegis ready at http://127.0.0.1:${port}`));
}).catch(error => { console.error(error); process.exit(1); });
