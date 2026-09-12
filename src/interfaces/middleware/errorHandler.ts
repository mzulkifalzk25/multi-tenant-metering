import type { NextFunction, Request, Response } from 'express';
import { ZodError } from 'zod';
import { isDomainError } from '../../shared/errors.js';

type AsyncRouteHandler = (req: Request, res: Response) => Promise<void>;

/** Express 4 does not catch rejected promises from async handlers itself; this forwards them to errorHandler. */
export const asyncHandler =
  (handler: AsyncRouteHandler) =>
  (req: Request, res: Response, next: NextFunction): void => {
    handler(req, res).catch(next);
  };

/** Centralized translation from thrown errors to HTTP responses. Must be registered last. */
// eslint-disable-next-line @typescript-eslint/no-unused-vars
export const errorHandler = (err: unknown, _req: Request, res: Response, _next: NextFunction): void => {
  if (isDomainError(err)) {
    res.status(err.statusCode).json({ error: err.message, code: err.code });
    return;
  }

  if (err instanceof ZodError) {
    res.status(400).json({ error: 'Validation failed', code: 'VALIDATION_ERROR', issues: err.issues });
    return;
  }

  const message = err instanceof Error ? err.message : 'Internal server error';
  res.status(500).json({ error: message, code: 'INTERNAL_ERROR' });
};
