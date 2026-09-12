import express from 'express';

const app = express();
const port = process.env['PORT'] ?? 3000;

app.get('/health', (_req, res) => {
  res.json({ status: 'ok' });
});

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`multi-tenant-metering listening on port ${port}`);
});
