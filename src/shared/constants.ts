import type { ResourceType } from './types.js';
import { asAmount, type Amount } from './types.js';

/** Default platform-level pool ceiling per resource type, used when seeding a new deployment. */
export const DEFAULT_POOL_LIMITS: Readonly<Record<ResourceType, Amount>> = {
  storage: asAmount(100 * 1024 * 1024 * 1024), // 100 GB, in bytes
  ai_tokens: asAmount(1_000_000),
  api_calls: asAmount(10_000),
};

/** Rate limiting windows, expressed in requests per window per resource type. */
export const RATE_LIMIT_WINDOW_MS = 60_000;

export const DEFAULT_RATE_LIMITS: Readonly<Record<ResourceType, number>> = {
  storage: 100,
  ai_tokens: 60,
  api_calls: 600,
};
