import assert from 'node:assert/strict';
import { test } from 'node:test';
import { BalanceRepository } from '../repositories/BalanceRepository.js';
import { asAmount, asTenantId, asUserId } from '../shared/types.js';
import {
  InMemoryAllocationRepository,
  InMemoryConsumptionRepository,
  InMemoryLedgerRepository,
} from './testHelpers.js';

const tenantId = asTenantId('tenant-1');
const userId = asUserId('user-1');

test('LedgerRepository (in-memory): append is the only mutation, entries accumulate in order', async () => {
  const repo = new InMemoryLedgerRepository();
  await repo.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(100),
    balance: asAmount(100),
  });
  await repo.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'consumed',
    amount: asAmount(30),
    balance: asAmount(70),
  });

  const entries = await repo.getAllForUser(tenantId, userId, 'storage');
  assert.equal(entries.length, 2);
  assert.equal(entries[0]?.entryType, 'allocated');
  assert.equal(entries[1]?.entryType, 'consumed');
});

test('LedgerRepository (in-memory): getAllForUser is scoped by tenant, user, and resource', async () => {
  const repo = new InMemoryLedgerRepository();
  const otherUser = asUserId('user-2');
  await repo.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(10),
    balance: asAmount(10),
  });
  await repo.append({
    tenantId,
    userId: otherUser,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(20),
    balance: asAmount(20),
  });
  await repo.append({
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType: 'allocated',
    amount: asAmount(30),
    balance: asAmount(30),
  });

  const entries = await repo.getAllForUser(tenantId, userId, 'storage');
  assert.equal(entries.length, 1);
  assert.equal(entries[0]?.amount, 10);
});

test('LedgerRepository (in-memory): getAllForTenant returns entries across all users', async () => {
  const repo = new InMemoryLedgerRepository();
  const otherUser = asUserId('user-2');
  await repo.append({
    tenantId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(500),
    balance: asAmount(500),
  });
  await repo.append({
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(200),
    balance: asAmount(200),
  });
  await repo.append({
    tenantId,
    userId: otherUser,
    resourceType: 'storage',
    entryType: 'allocated',
    amount: asAmount(100),
    balance: asAmount(100),
  });

  const entries = await repo.getAllForTenant(tenantId);
  assert.equal(entries.length, 3);
});

test('AllocationRepository (in-memory): setAllocated upserts, keyed by scope+resource', async () => {
  const repo = new InMemoryAllocationRepository();
  const created = await repo.setAllocated(tenantId, userId, 'storage', asAmount(100));
  assert.equal(created.allocated, 100);

  const updated = await repo.setAllocated(tenantId, userId, 'storage', asAmount(250));
  assert.equal(updated.allocated, 250);
  assert.equal(updated.id, created.id, 'the same scope+resource must update, not duplicate, the row');

  const found = await repo.findByScope(tenantId, userId, 'storage');
  assert.equal(found?.allocated, 250);
});

test('AllocationRepository (in-memory): listByTenant returns both tenant- and user-level rows', async () => {
  const repo = new InMemoryAllocationRepository();
  await repo.setAllocated(tenantId, undefined, 'storage', asAmount(1000));
  await repo.setAllocated(tenantId, userId, 'storage', asAmount(200));

  const rows = await repo.listByTenant(tenantId, 'storage');
  assert.equal(rows.length, 2);
});

test('ConsumptionRepository (in-memory): increment accumulates rather than overwriting', async () => {
  const repo = new InMemoryConsumptionRepository();
  await repo.increment(tenantId, userId, 'api_calls', asAmount(5));
  const result = await repo.increment(tenantId, userId, 'api_calls', asAmount(7));

  assert.equal(result.consumed, 12);
});

test('BalanceRepository: getBalance replays the ledger for a scope+resource', async () => {
  const ledgerRepository = new InMemoryLedgerRepository();
  await ledgerRepository.append({
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType: 'allocated',
    amount: asAmount(1000),
    balance: asAmount(1000),
  });
  await ledgerRepository.append({
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType: 'consumed',
    amount: asAmount(400),
    balance: asAmount(600),
  });

  const balanceRepository = new BalanceRepository(ledgerRepository);
  const balance = await balanceRepository.getBalance(tenantId, userId, 'ai_tokens');

  assert.equal(balance.allocated, 1000);
  assert.equal(balance.consumed, 400);
  assert.equal(balance.available, 600);
});
