import { createApp } from './frameworks/express.js';
import { logger } from './shared/logger.js';

const port = Number(process.env['PORT'] ?? 3000);
const app = createApp();

app.listen(port, () => {
  logger.info(`multi-tenant-metering listening on port ${port}`);
});
