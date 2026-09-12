import assert from 'node:assert/strict';
import { test } from 'node:test';
import type { Request, Response } from 'express';
import jwt from 'jsonwebtoken';
import { z } from 'zod';
import { BalanceController } from '../interfaces/controllers/BalanceController.js';
import { HealthController } from '../interfaces/controllers/HealthController.js';
import { QuotaController } from '../interfaces/controllers/QuotaController.js';
import { authMiddleware } from '../interfaces/middleware/auth.js';
import { asyncHandler, errorHandler } from '../interfaces/middleware/errorHandler.js';
import { createRateLimitMiddleware, RateLimiter } from '../interfaces/middleware/rateLimiter.js';
import { AllocateQuota } from '../use-cases/AllocateQuota.js';
import { GetAllocationHistory } from '../use-cases/GetAllocationHistory.js';
import { GetBalance } from '../use-cases/GetBalance.js';
import { RecordUsage } from '../use-cases/RecordUsage.js';
import { ReserveQuota } from '../use-cases/ReserveQuota.js';
import { ScopeValidator } from '../use-cases/ScopeValidator.js';
import { QuotaExhaustedError, ValidationError } from '../shared/errors.js';
import { asAmount, asTenantId, asUserId } from '../shared/types.js';
import {
  InMemoryAllocationRepository,
  InMemoryConsumptionRepository,
  InMemoryLedgerRepository,
} from './testHelpers.js';

process.env['JWT_SECRET'] = 'test-secret';

const tenantId = asTenantId('tenant-1');
const userId = asUserId('user-1');

interface MockResponse {
  statusCode: number;
  body: unknown;
  res: Response;
}

function mockResponse(): MockResponse {
  const state: MockResponse = { statusCode: 200, body: undefined, res: undefined as unknown as Response };
  const res = {
    status(code: number) {
      state.statusCode = code;
      return res;
    },
    json(payload: unknown) {
      state.body = payload;
      return res;
    },
  } as unknown as Response;
  state.res = res;
  return state;
}

function mockRequest(overrides: Record<string, unknown> = {}): Request {
  return { headers: {}, body: {}, query: {}, ...overrides } as unknown as Request;
}

test('HealthController: reports ok with a timestamp', () => {
  const controller = new HealthController();
  const response = mockResponse();
  controller.check(mockRequest(), response.res);
  assert.equal((response.body as { status: string }).status, 'ok');
});

test('authMiddleware: rejects a request with no Authorization header', () => {
  const response = mockResponse();
  authMiddleware(mockRequest(), response.res, () => assert.fail('next should not be called'));
  assert.equal(response.statusCode, 401);
  assert.match((response.body as { error: string }).error, /Authorization/);
});

test('authMiddleware: rejects an invalid token', () => {
  const response = mockResponse();
  const req = mockRequest({ headers: { authorization: 'Bearer not-a-real-token' } });
  authMiddleware(req, response.res, () => assert.fail('next should not be called'));
  assert.equal(response.statusCode, 401);
});

test('authMiddleware: attaches a Principal for a valid token and calls next', () => {
  const token = jwt.sign({ role: 'tenant_admin', tenantId }, process.env['JWT_SECRET']!);
  const req = mockRequest({ headers: { authorization: `Bearer ${token}` } });
  const response = mockResponse();

  let nextCalled = false;
  authMiddleware(req, response.res, () => {
    nextCalled = true;
  });

  assert.equal(nextCalled, true);
  assert.equal((req as unknown as { principal: { role: string } }).principal.role, 'tenant_admin');
});

test('errorHandler: maps a DomainError to its declared status code and machine-readable code', () => {
  const response = mockResponse();
  errorHandler(new QuotaExhaustedError('no budget left'), mockRequest(), response.res, () => undefined);
  assert.equal(response.statusCode, 429);
  assert.equal((response.body as { code: string }).code, 'QUOTA_EXHAUSTED');
});

test('errorHandler: maps a ZodError to 400 with validation issues', () => {
  const schema = z.object({ amount: z.number() });
  const response = mockResponse();
  const result = schema.safeParse({ amount: 'not-a-number' });
  assert.equal(result.success, false);
  if (!result.success) {
    errorHandler(result.error, mockRequest(), response.res, () => undefined);
  }
  assert.equal(response.statusCode, 400);
  assert.equal((response.body as { code: string }).code, 'VALIDATION_ERROR');
});

test('errorHandler: falls back to 500 for an unrecognized error', () => {
  const response = mockResponse();
  errorHandler(new Error('boom'), mockRequest(), response.res, () => undefined);
  assert.equal(response.statusCode, 500);
});

test('asyncHandler: forwards a rejected promise to next() instead of throwing', async () => {
  const response = mockResponse();
  let forwarded: unknown;
  const handler = asyncHandler(async () => {
    throw new ValidationError('bad input');
  });

  await new Promise<void>((resolve) => {
    handler(mockRequest(), response.res, (err) => {
      forwarded = err;
      resolve();
    });
  });

  assert.ok(forwarded instanceof ValidationError);
});

test('RateLimiter: allows calls under the limit and blocks once exceeded', () => {
  const limiter = new RateLimiter({ storage: 2, ai_tokens: 2, api_calls: 2 }, 60_000);
  const now = 1_000;

  assert.equal(limiter.tryConsume('t1', 'u1', 'storage', now), true);
  assert.equal(limiter.tryConsume('t1', 'u1', 'storage', now), true);
  assert.equal(limiter.tryConsume('t1', 'u1', 'storage', now), false);
});

test('RateLimiter: a new window resets the count', () => {
  const limiter = new RateLimiter({ storage: 1, ai_tokens: 1, api_calls: 1 }, 1000);
  assert.equal(limiter.tryConsume('t1', 'u1', 'storage', 0), true);
  assert.equal(limiter.tryConsume('t1', 'u1', 'storage', 500), false);
  assert.equal(limiter.tryConsume('t1', 'u1', 'storage', 2000), true);
});

test('createRateLimitMiddleware: passes through when no resourceType/principal is present', () => {
  const middleware = createRateLimitMiddleware(new RateLimiter());
  let nextCalled = false;
  middleware(mockRequest(), mockResponse().res, () => {
    nextCalled = true;
  });
  assert.equal(nextCalled, true);
});

test('QuotaController: reserve, record, and allocate happy paths against in-memory repositories', async () => {
  const ledger = new InMemoryLedgerRepository();
  const allocations = new InMemoryAllocationRepository();
  const consumption = new InMemoryConsumptionRepository();
  const controller = new QuotaController(
    new ReserveQuota(ledger),
    new RecordUsage(ledger, consumption),
    new AllocateQuota(ledger, allocations),
    new ScopeValidator()
  );
  const principal = { role: 'platform_admin' as const };

  const allocateTenantReq = mockRequest({
    body: { tenantId, resourceType: 'storage', amount: 1000 },
    principal,
  });
  const allocateTenantRes = mockResponse();
  await controller.allocate(allocateTenantReq, allocateTenantRes.res);
  assert.equal(allocateTenantRes.statusCode, 200);

  const allocateUserReq = mockRequest({
    body: { tenantId, userId, resourceType: 'storage', amount: 500 },
    principal,
  });
  const allocateUserRes = mockResponse();
  await controller.allocate(allocateUserReq, allocateUserRes.res);
  assert.equal(allocateUserRes.statusCode, 200);

  const reserveReq = mockRequest({ body: { tenantId, userId, resourceType: 'storage' }, principal });
  const reserveRes = mockResponse();
  await controller.reserve(reserveReq, reserveRes.res);
  assert.deepEqual(reserveRes.body, { ok: true });

  const recordReq = mockRequest({
    body: { tenantId, userId, resourceType: 'storage', amount: 100 },
    principal,
  });
  const recordRes = mockResponse();
  await controller.record(recordReq, recordRes.res);
  assert.equal((recordRes.body as { recordedAmount: number }).recordedAmount, 100);
});

test('BalanceController: balance and history endpoints against in-memory repositories', async () => {
  const ledger = new InMemoryLedgerRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(500),
    balance: asAmount(500),
  });
  const controller = new BalanceController(
    new GetBalance(ledger),
    new GetAllocationHistory(ledger),
    new ScopeValidator()
  );
  const principal = { role: 'platform_admin' as const };

  const balanceRes = mockResponse();
  await controller.balance(
    mockRequest({ query: { tenantId, userId, resourceType: 'storage' }, principal }),
    balanceRes.res
  );
  assert.equal((balanceRes.body as { balance: { allocated: number } }).balance.allocated, 500);

  const historyRes = mockResponse();
  await controller.history(mockRequest({ query: { tenantId, resourceType: 'storage' }, principal }), historyRes.res);
  assert.equal((historyRes.body as { entries: unknown[] }).entries.length, 1);
});
