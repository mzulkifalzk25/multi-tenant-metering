import assert from 'node:assert/strict';
import { test } from 'node:test';
import { AllocationEntity } from '../entities/Allocation.js';
import { BalanceEntity } from '../entities/Balance.js';
import { LedgerEntity, replayLedger } from '../entities/Ledger.js';
import { QuotaPoolEntity } from '../entities/QuotaPool.js';
import { asAllocationId, asAmount, asLedgerId, asPoolId, asTenantId, asUserId, zeroAmount } from '../shared/types.js';

const tenantId = asTenantId('tenant-1');
const userId = asUserId('user-1');

test('AllocationEntity: canCoverChildAllocation allows a sub-allocation within remaining budget', () => {
  const allocation = new AllocationEntity({
    id: asAllocationId('alloc-1'),
    tenantId,
    resourceType: 'storage',
    allocated: asAmount(1000),
    createdAt: new Date(),
    updatedAt: new Date(),
  });

  assert.equal(allocation.canCoverChildAllocation(asAmount(500), asAmount(400)), true);
  assert.equal(allocation.canCoverChildAllocation(asAmount(500), asAmount(600)), false);
});

test('AllocationEntity: withTopUp increases allocated, withReduction never goes negative', () => {
  const allocation = new AllocationEntity({
    id: asAllocationId('alloc-1'),
    tenantId,
    resourceType: 'storage',
    allocated: asAmount(100),
    createdAt: new Date(),
    updatedAt: new Date(),
  });

  assert.equal(allocation.withTopUp(asAmount(50)).allocated, 150);
  assert.equal(allocation.withReduction(asAmount(1000)).allocated, 0);
});

test('AllocationEntity: level() reports tenant vs. user scope', () => {
  const tenantLevel = new AllocationEntity({
    id: asAllocationId('a'),
    tenantId,
    resourceType: 'storage',
    allocated: zeroAmount,
    createdAt: new Date(),
    updatedAt: new Date(),
  });
  const userLevel = new AllocationEntity({ ...tenantLevel, userId });

  assert.equal(tenantLevel.level(), 'tenant');
  assert.equal(userLevel.level(), 'user');
});

test('replayLedger: folds allocated/consumed/deallocated into totals, ignoring reserved', () => {
  const entries = [
    entry('allocated', 1000, 1000),
    entry('consumed', 200, 800),
    entry('reserved', 0, 800),
    entry('deallocated', 100, 700),
    entry('consumed', 50, 650),
  ];

  const result = replayLedger(entries);

  assert.equal(result.allocated, 900); // 1000 - 100
  assert.equal(result.consumed, 250); // 200 + 50
  assert.equal(result.available, 650);
});

test('replayLedger: consumption never drives available below zero', () => {
  const entries = [entry('allocated', 100, 100), entry('consumed', 100, 0), entry('consumed', 50, 0)];
  const result = replayLedger(entries);
  assert.equal(result.available, 0);
});

test('BalanceEntity.fromLedger: reconstructs balance from a full history', () => {
  const entries = [entry('allocated', 500, 500), entry('consumed', 120, 380)];
  const balance = BalanceEntity.fromLedger({ tenantId, userId }, 'ai_tokens', entries);

  assert.equal(balance.allocated, 500);
  assert.equal(balance.consumed, 120);
  assert.equal(balance.available, 380);
  assert.equal(balance.isExhausted(), false);
});

test('BalanceEntity: isExhausted is true once available hits zero', () => {
  const balance = BalanceEntity.fromLedger({ tenantId, userId }, 'ai_tokens', [
    entry('allocated', 100, 100),
    entry('consumed', 100, 0),
  ]);
  assert.equal(balance.isExhausted(), true);
});

test('BalanceEntity: clampToAvailable caps a requested amount at what remains', () => {
  const balance = BalanceEntity.fromLedger({ tenantId, userId }, 'api_calls', [
    entry('allocated', 100, 100),
    entry('consumed', 80, 20),
  ]);
  assert.equal(balance.clampToAvailable(asAmount(50)), 20);
  assert.equal(balance.clampToAvailable(asAmount(5)), 5);
});

test('QuotaPoolEntity: canAllocate and remaining respect capacity', () => {
  const pool = new QuotaPoolEntity({
    id: asPoolId('pool-1'),
    resourceType: 'storage',
    capacity: asAmount(1000),
    allocatedToTenants: asAmount(700),
  });

  assert.equal(pool.remaining(), 300);
  assert.equal(pool.canAllocate(asAmount(300)), true);
  assert.equal(pool.canAllocate(asAmount(301)), false);
});

test('LedgerEntity: entries are terminal', () => {
  const ledgerEntry = new LedgerEntity({
    id: asLedgerId('l-1'),
    tenantId,
    userId,
    resourceType: 'storage',
    entryType: 'consumed',
    amount: asAmount(1),
    balance: asAmount(1),
    createdAt: new Date(),
  });
  assert.equal(ledgerEntry.isTerminal(), true);
});

function entry(entryType: 'allocated' | 'deallocated' | 'consumed' | 'reserved', amount: number, balance: number) {
  return new LedgerEntity({
    id: asLedgerId(`l-${Math.random()}`),
    tenantId,
    userId,
    resourceType: 'ai_tokens',
    entryType,
    amount: asAmount(amount),
    balance: asAmount(balance),
    createdAt: new Date(),
  });
}
