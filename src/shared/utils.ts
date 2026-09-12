import { randomUUID } from 'node:crypto';

/** Generates a v4 UUID string, used as the opaque backing value for every branded id. */
export const generateId = (): string => randomUUID();

/** Clamps `value` to the inclusive range [min, max]. */
export const clamp = (value: number, min: number, max: number): number => Math.min(Math.max(value, min), max);
