import type { Request, Response } from 'express';

/** GET /health — liveness probe. Deliberately has no dependencies to check. */
export class HealthController {
  check = (_req: Request, res: Response): void => {
    res.json({ status: 'ok', timestamp: new Date().toISOString() });
  };
}
