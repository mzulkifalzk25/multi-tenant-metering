import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AllocateQuota } from '../use-cases/AllocateQuota.js';
import { GetAllocationHistory } from '../use-cases/GetAllocationHistory.js';
import { GetBalance } from '../use-cases/GetBalance.js';
import { RecordUsage } from '../use-cases/RecordUsage.js';
import { ReserveQuota } from '../use-cases/ReserveQuota.js';
import { ScopeValidator } from '../use-cases/ScopeValidator.js';
import { AllocationInvariantError, QuotaExhaustedError, ScopeAccessError } from '../shared/errors.js';
import { asAmount, asTenantId, asUserId } from '../shared/types.js';
import {
  InMemoryAllocationRepository,
  InMemoryConsumptionRepository,
  InMemoryLedgerRepository,
} from './testHelpers.js';

const tenantId = asTenantId('tenant-1');
const userId = asUserId('user-1');

test('ReserveQuota: allows the operation while any balance remains', async () => {
  const ledger = new InMemoryLedgerRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType: 'allocated',
    amount: asAmount(100),
    balance: asAmount(100),
  });

  const reserveQuota = new ReserveQuota(ledger);
  const allowed = await reserveQuota.execute({ tenantId, userId, resourceType: 'ai_tokens' });

  assert.equal(allowed, true);
  const recorded = await ledger.getAllForUser(tenantId, userId, 'ai_tokens');
  assert.equal(recorded.at(-1)?.entryType, 'reserved', 'a reservation should be recorded for audit visibility');
});

test('ReserveQuota: refuses once the available balance is exactly zero', async () => {
  const ledger = new InMemoryLedgerRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType: 'allocated',
    amount: asAmount(100),
    balance: asAmount(100),
  });
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType: 'consumed',
    amount: asAmount(100),
    balance: asAmount(0),
  });

  const reserveQuota = new ReserveQuota(ledger);
  await assert.rejects(
    () => reserveQuota.execute({ tenantId, userId, resourceType: 'ai_tokens' }),
    QuotaExhaustedError
  );
});

test('ReserveQuota: refuses with no allocation at all (balance starts at zero)', async () => {
  const reserveQuota = new ReserveQuota(new InMemoryLedgerRepository());
  await assert.rejects(
    () => reserveQuota.execute({ tenantId, userId, resourceType: 'ai_tokens' }),
    QuotaExhaustedError
  );
});

test('RecordUsage: records the full amount when it fits within the balance', async () => {
  const ledger = new InMemoryLedgerRepository();
  const consumption = new InMemoryConsumptionRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(1000),
    balance: asAmount(1000),
  });

  const recordUsage = new RecordUsage(ledger, consumption);
  const result = await recordUsage.execute({ tenantId, userId, resourceType: 'storage', amount: 250 });

  assert.equal(result.recordedAmount, 250);
  assert.equal(result.balanceAfter, 750);
  const consumptionRow = await consumption.findByScope(tenantId, userId, 'storage');
  assert.equal(consumptionRow?.consumed, 250);
});

test('RecordUsage: clamps an overshoot to whatever headroom remains, never going negative', async () => {
  const ledger = new InMemoryLedgerRepository();
  const consumption = new InMemoryConsumptionRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(100),
    balance: asAmount(100),
  });

  const recordUsage = new RecordUsage(ledger, consumption);
  const result = await recordUsage.execute({ tenantId, userId, resourceType: 'storage', amount: 9999 });

  assert.equal(result.recordedAmount, 100, 'only the remaining 100 should ever be charged');
  assert.equal(result.balanceAfter, 0);
});

test('RecordUsage: recording zero-available usage records zero and does not go negative', async () => {
  const ledger = new InMemoryLedgerRepository();
  const consumption = new InMemoryConsumptionRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(10),
    balance: asAmount(10),
  });
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'consumed',
    amount: asAmount(10),
    balance: asAmount(0),
  });

  const recordUsage = new RecordUsage(ledger, consumption);
  const result = await recordUsage.execute({ tenantId, userId, resourceType: 'storage', amount: 50 });

  assert.equal(result.recordedAmount, 0);
  assert.equal(result.balanceAfter, 0);
});

test('GetBalance: reconstructs the same numbers RecordUsage produced', async () => {
  const ledger = new InMemoryLedgerRepository();
  const consumption = new InMemoryConsumptionRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'api_calls',
    entryType: 'allocated',
    amount: asAmount(500),
    balance: asAmount(500),
  });
  await new RecordUsage(ledger, consumption).execute({ tenantId, userId, resourceType: 'api_calls', amount: 120 });

  const balance = await new GetBalance(ledger).execute({ tenantId, userId, resourceType: 'api_calls' });

  assert.equal(balance.allocated, 500);
  assert.equal(balance.consumed, 120);
  assert.equal(balance.available, 380);
});

test('GetBalance.getHistory: returns every ledger entry behind the balance, in order', async () => {
  const ledger = new InMemoryLedgerRepository();
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'api_calls',
    entryType: 'allocated',
    amount: asAmount(500),
    balance: asAmount(500),
  });
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'api_calls',
    entryType: 'consumed',
    amount: asAmount(50),
    balance: asAmount(450),
  });

  const history = await new GetBalance(ledger).getHistory({ tenantId, userId, resourceType: 'api_calls' });

  assert.equal(history.length, 2);
  assert.equal(history[0]?.entryType, 'allocated');
  assert.equal(history[1]?.entryType, 'consumed');
});

test('GetAllocationHistory: returns the tenant-wide ledger, including all of its users', async () => {
  const ledger = new InMemoryLedgerRepository();
  const otherUser = asUserId('user-2');
  await ledger.append({
    tenantId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(1000),
    balance: asAmount(1000),
  });
  await ledger.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(400),
    balance: asAmount(400),
  });
  await ledger.append({
    tenantId,
    userId: otherUser,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(300),
    balance: asAmount(300),
  });

  const history = await new GetAllocationHistory(ledger).execute({ tenantId, resourceType: 'storage' });

  assert.equal(history.length, 3);
});

test('AllocateQuota: allocating to the tenant itself always succeeds and appends an `allocated` entry', async () => {
  const ledger = new InMemoryLedgerRepository();
  const allocations = new InMemoryAllocationRepository();
  const allocateQuota = new AllocateQuota(ledger, allocations);

  const result = await allocateQuota.execute({ tenantId, resourceType: 'storage', amount: 1000 });

  assert.equal(result.allocated, 1000);
  const entries = await ledger.getAllForTenant(tenantId, 'storage');
  assert.equal(entries.at(-1)?.entryType, 'allocated');
});

test('AllocateQuota: sub-allocating to a user within the tenant budget succeeds', async () => {
  const ledger = new InMemoryLedgerRepository();
  const allocations = new InMemoryAllocationRepository();
  const allocateQuota = new AllocateQuota(ledger, allocations);

  await allocateQuota.execute({ tenantId, resourceType: 'storage', amount: 1000 });
  const userAllocation = await allocateQuota.execute({ tenantId, userId, resourceType: 'storage', amount: 400 });

  assert.equal(userAllocation.allocated, 400);
});

test('AllocateQuota: refuses a sub-allocation that would exceed the tenant`s own budget', async () => {
  const ledger = new InMemoryLedgerRepository();
  const allocations = new InMemoryAllocationRepository();
  const allocateQuota = new AllocateQuota(ledger, allocations);
  const otherUser = asUserId('user-2');

  await allocateQuota.execute({ tenantId, resourceType: 'storage', amount: 1000 });
  await allocateQuota.execute({ tenantId, userId, resourceType: 'storage', amount: 700 });

  await assert.rejects(
    () => allocateQuota.execute({ tenantId, userId: otherUser, resourceType: 'storage', amount: 400 }),
    AllocationInvariantError
  );
});

test('AllocateQuota: reducing a user allocation (negative delta) never triggers the invariant check', async () => {
  const ledger = new InMemoryLedgerRepository();
  const allocations = new InMemoryAllocationRepository();
  const allocateQuota = new AllocateQuota(ledger, allocations);

  await allocateQuota.execute({ tenantId, resourceType: 'storage', amount: 1000 });
  await allocateQuota.execute({ tenantId, userId, resourceType: 'storage', amount: 900 });
  const reduced = await allocateQuota.execute({ tenantId, userId, resourceType: 'storage', amount: -300 });

  assert.equal(reduced.allocated, 600);
});

test('ScopeValidator: a plain user may only access their own scope', () => {
  const validator = new ScopeValidator();
  const otherUser = asUserId('user-2');

  assert.doesNotThrow(() => validator.assertCanAccess({ role: 'user', tenantId, userId }, { tenantId, userId }));
  assert.throws(
    () => validator.assertCanAccess({ role: 'user', tenantId, userId }, { tenantId, userId: otherUser }),
    ScopeAccessError
  );
});

test('ScopeValidator: a tenant admin may access any user within their own tenant, but no other tenant', () => {
  const validator = new ScopeValidator();
  const otherTenant = asTenantId('tenant-2');
  const anyUser = asUserId('user-99');

  assert.doesNotThrow(() =>
    validator.assertCanAccess({ role: 'tenant_admin', tenantId }, { tenantId, userId: anyUser })
  );
  assert.throws(
    () => validator.assertCanAccess({ role: 'tenant_admin', tenantId }, { tenantId: otherTenant }),
    ScopeAccessError
  );
});

test('ScopeValidator: a platform admin may access any tenant or user', () => {
  const validator = new ScopeValidator();
  const otherTenant = asTenantId('tenant-2');

  assert.doesNotThrow(() => validator.assertCanAccess({ role: 'platform_admin' }, { tenantId: otherTenant, userId }));
});
