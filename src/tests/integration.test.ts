import assert from 'node:assert/strict';
import { randomUUID } from 'node:crypto';
import { after, test } from 'node:test';
import { AllocationRepository } from '../repositories/AllocationRepository.js';
import { ConsumptionRepository } from '../repositories/ConsumptionRepository.js';
import { LedgerRepository } from '../repositories/LedgerRepository.js';
import { AllocateQuota } from '../use-cases/AllocateQuota.js';
import { GetAllocationHistory } from '../use-cases/GetAllocationHistory.js';
import { GetBalance } from '../use-cases/GetBalance.js';
import { RecordUsage } from '../use-cases/RecordUsage.js';
import { ReserveQuota } from '../use-cases/ReserveQuota.js';
import { closeDb } from '../frameworks/database.js';
import { asTenantId, asUserId } from '../shared/types.js';
import { AllocationInvariantError, QuotaExhaustedError } from '../shared/errors.js';

/**
 * These tests hit a real PostgreSQL instance end to end: Drizzle-backed
 * repositories, real INSERT/SELECT, real transactions of the reserve ->
 * record -> balance flow. They are skipped unless a database is reachable
 * (set DATABASE_URL and run `npm run test:integration`, or `npm run db:up`
 * first) so that `npm test` stays usable without Docker/Postgres installed.
 */
const shouldRun = Boolean(process.env['DATABASE_URL']);
const describeOrSkip = shouldRun ? test : test.skip;

describeOrSkip('Integration: Reserve -> Record -> Balance against real PostgreSQL', async (t) => {
  const ledgerRepository = new LedgerRepository();
  const allocationRepository = new AllocationRepository();
  const consumptionRepository = new ConsumptionRepository();

  const reserveQuota = new ReserveQuota(ledgerRepository);
  const recordUsage = new RecordUsage(ledgerRepository, consumptionRepository);
  const allocateQuota = new AllocateQuota(ledgerRepository, allocationRepository);
  const getBalance = new GetBalance(ledgerRepository);
  const getAllocationHistory = new GetAllocationHistory(ledgerRepository);

  await t.test('the full lifecycle: allocate -> reserve -> record -> balance -> history', async () => {
    const tenantId = asTenantId(`tenant-${randomUUID()}`);
    const userId = asUserId(`user-${randomUUID()}`);

    await allocateQuota.execute({ tenantId, resourceType: 'storage', amount: 1000 });
    await allocateQuota.execute({ tenantId, userId, resourceType: 'storage', amount: 1000 });

    const canProceed = await reserveQuota.execute({ tenantId, userId, resourceType: 'storage' });
    assert.equal(canProceed, true);

    const { recordedAmount, balanceAfter } = await recordUsage.execute({
      tenantId,
      userId,
      resourceType: 'storage',
      amount: 250,
      reason: 'integration test upload',
    });
    assert.equal(recordedAmount, 250);
    assert.equal(balanceAfter, 750);

    const balance = await getBalance.execute({ tenantId, userId, resourceType: 'storage' });
    assert.equal(balance.allocated, 1000);
    assert.equal(balance.consumed, 250);
    assert.equal(balance.available, 750);

    const history = await getAllocationHistory.execute({ tenantId, resourceType: 'storage' });
    const entryTypes = history.map((entry) => entry.entryType);
    assert.deepEqual(entryTypes, ['allocated', 'allocated', 'reserved', 'consumed']);
  });

  await t.test('overshooting the balance clamps the recorded amount instead of going negative', async () => {
    const tenantId = asTenantId(`tenant-${randomUUID()}`);
    const userId = asUserId(`user-${randomUUID()}`);

    await allocateQuota.execute({ tenantId, resourceType: 'ai_tokens', amount: 500 });
    await allocateQuota.execute({ tenantId, userId, resourceType: 'ai_tokens', amount: 100 });

    const result = await recordUsage.execute({ tenantId, userId, resourceType: 'ai_tokens', amount: 9999 });
    assert.equal(result.recordedAmount, 100);
    assert.equal(result.balanceAfter, 0);

    await assert.rejects(
      () => reserveQuota.execute({ tenantId, userId, resourceType: 'ai_tokens' }),
      QuotaExhaustedError
    );
  });

  await t.test('a dispute is resolved by replaying the persisted ledger and matches the stored balance', async () => {
    const tenantId = asTenantId(`tenant-${randomUUID()}`);
    const userId = asUserId(`user-${randomUUID()}`);

    await allocateQuota.execute({ tenantId, resourceType: 'api_calls', amount: 300 });
    await allocateQuota.execute({ tenantId, userId, resourceType: 'api_calls', amount: 300 });
    await recordUsage.execute({ tenantId, userId, resourceType: 'api_calls', amount: 40 });
    await recordUsage.execute({ tenantId, userId, resourceType: 'api_calls', amount: 60 });

    const history = await getBalance.getHistory({ tenantId, userId, resourceType: 'api_calls' });
    const replayedConsumed = history.filter((e) => e.entryType === 'consumed').reduce((sum, e) => sum + e.amount, 0);

    const balance = await getBalance.execute({ tenantId, userId, resourceType: 'api_calls' });
    assert.equal(replayedConsumed, balance.consumed);
    assert.equal(balance.consumed, 100);
  });

  await t.test('a tenant cannot sub-allocate more to its users than it was itself allocated', async () => {
    const tenantId = asTenantId(`tenant-${randomUUID()}`);
    const userId = asUserId(`user-${randomUUID()}`);

    await allocateQuota.execute({ tenantId, resourceType: 'storage', amount: 100 });

    await assert.rejects(
      () => allocateQuota.execute({ tenantId, userId, resourceType: 'storage', amount: 500 }),
      AllocationInvariantError
    );
  });

  after(async () => {
    await closeDb();
  });
});
