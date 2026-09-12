import { z } from 'zod';
import { RESOURCE_TYPES } from './types.js';

export const resourceTypeSchema = z.enum(RESOURCE_TYPES);

export const scopeSchema = z.object({
  tenantId: z.string().min(1),
  userId: z.string().min(1).optional(),
});

export const reserveQuotaRequestSchema = z.object({
  tenantId: z.string().min(1),
  userId: z.string().min(1),
  resourceType: resourceTypeSchema,
});

export const recordUsageRequestSchema = z.object({
  tenantId: z.string().min(1),
  userId: z.string().min(1),
  resourceType: resourceTypeSchema,
  amount: z.number().finite().nonnegative(),
  reason: z.string().min(1).optional(),
});

export const balanceRequestSchema = z.object({
  tenantId: z.string().min(1),
  userId: z.string().min(1),
  resourceType: resourceTypeSchema,
});

export const allocateRequestSchema = z.object({
  tenantId: z.string().min(1),
  userId: z.string().min(1).optional(),
  resourceType: resourceTypeSchema,
  amount: z.number().finite().nonnegative(),
  reason: z.string().min(1).optional(),
});
