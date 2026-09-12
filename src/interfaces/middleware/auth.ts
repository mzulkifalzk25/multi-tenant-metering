import type { NextFunction, Request, Response } from 'express';
import { verifyToken } from '../../frameworks/auth.js';
import { asTenantId, asUserId } from '../../shared/types.js';
import type { Principal } from '../../use-cases/ScopeValidator.js';

export interface AuthenticatedRequest extends Request {
  principal: Principal;
}

const BEARER_PREFIX = 'Bearer ';

/** Verifies the bearer JWT on every request and attaches the resulting Principal. */
export const authMiddleware = (req: Request, res: Response, next: NextFunction): void => {
  const header = req.headers['authorization'];
  if (!header?.startsWith(BEARER_PREFIX)) {
    res.status(401).json({ error: 'Missing or malformed Authorization header' });
    return;
  }

  try {
    const token = header.slice(BEARER_PREFIX.length);
    const payload = verifyToken(token);
    const principal: Principal = {
      role: payload.role,
      tenantId: payload.tenantId ? asTenantId(payload.tenantId) : undefined,
      userId: payload.userId ? asUserId(payload.userId) : undefined,
    };
    (req as AuthenticatedRequest).principal = principal;
    next();
  } catch {
    res.status(401).json({ error: 'Invalid or expired token' });
  }
};
