import type { NextFunction, Request, Response } from 'express';
import { DEFAULT_RATE_LIMITS, RATE_LIMIT_WINDOW_MS } from '../../shared/constants.js';
import { RESOURCE_TYPES, type ResourceType } from '../../shared/types.js';
import type { AuthenticatedRequest } from './auth.js';

interface WindowState {
  count: number;
  windowStartedAt: number;
}

/**
 * A simple fixed-window limiter, keyed by tenant/user/resource. In-process
 * state is fine for a single instance; a multi-instance deployment would
 * back this with Redis instead, but the interface (one function you call
 * before the route handler) would stay the same.
 */
export class RateLimiter {
  private readonly windows = new Map<string, WindowState>();

  constructor(
    private readonly limits: Readonly<Record<ResourceType, number>> = DEFAULT_RATE_LIMITS,
    private readonly windowMs: number = RATE_LIMIT_WINDOW_MS
  ) {}

  private keyFor(tenantId: string, userId: string | undefined, resourceType: ResourceType): string {
    return `${tenantId}:${userId ?? '-'}:${resourceType}`;
  }

  /** Returns true if the call is allowed under the current window, incrementing its counter as a side effect. */
  tryConsume(
    tenantId: string,
    userId: string | undefined,
    resourceType: ResourceType,
    now: number = Date.now()
  ): boolean {
    const key = this.keyFor(tenantId, userId, resourceType);
    const limit = this.limits[resourceType];
    const state = this.windows.get(key);

    if (!state || now - state.windowStartedAt >= this.windowMs) {
      this.windows.set(key, { count: 1, windowStartedAt: now });
      return true;
    }

    if (state.count >= limit) {
      return false;
    }

    state.count += 1;
    return true;
  }
}

const parseResourceTypeOrUndefined = (value: unknown): ResourceType | undefined =>
  typeof value === 'string' && (RESOURCE_TYPES as readonly string[]).includes(value)
    ? (value as ResourceType)
    : undefined;

export const createRateLimitMiddleware = (limiter: RateLimiter) => {
  return (req: Request, res: Response, next: NextFunction): void => {
    const resourceType = parseResourceTypeOrUndefined(req.body?.resourceType ?? req.query['resourceType']);
    const principal = (req as AuthenticatedRequest).principal;

    if (!resourceType || !principal?.tenantId) {
      next();
      return;
    }

    const allowed = limiter.tryConsume(principal.tenantId, principal.userId, resourceType);
    if (!allowed) {
      res.status(429).json({ error: 'Rate limit exceeded', code: 'RATE_LIMIT_EXCEEDED' });
      return;
    }

    next();
  };
};
