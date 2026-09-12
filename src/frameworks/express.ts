import express, { type Express } from 'express';
import { BalanceController } from '../interfaces/controllers/BalanceController.js';
import { HealthController } from '../interfaces/controllers/HealthController.js';
import { QuotaController } from '../interfaces/controllers/QuotaController.js';
import { authMiddleware } from '../interfaces/middleware/auth.js';
import { asyncHandler, errorHandler } from '../interfaces/middleware/errorHandler.js';
import { requestLogger } from '../interfaces/middleware/logging.js';
import { createRateLimitMiddleware, RateLimiter } from '../interfaces/middleware/rateLimiter.js';
import { AllocationRepository } from '../repositories/AllocationRepository.js';
import { ConsumptionRepository } from '../repositories/ConsumptionRepository.js';
import { LedgerRepository } from '../repositories/LedgerRepository.js';
import { AllocateQuota } from '../use-cases/AllocateQuota.js';
import { GetAllocationHistory } from '../use-cases/GetAllocationHistory.js';
import { GetBalance } from '../use-cases/GetBalance.js';
import { RecordUsage } from '../use-cases/RecordUsage.js';
import { ReserveQuota } from '../use-cases/ReserveQuota.js';
import { ScopeValidator } from '../use-cases/ScopeValidator.js';

/** Wires repositories -> use cases -> controllers and mounts routes. Pure composition, no side effects beyond `express()`. */
export const createApp = (): Express => {
  const ledgerRepository = new LedgerRepository();
  const allocationRepository = new AllocationRepository();
  const consumptionRepository = new ConsumptionRepository();

  const reserveQuota = new ReserveQuota(ledgerRepository);
  const recordUsage = new RecordUsage(ledgerRepository, consumptionRepository);
  const allocateQuota = new AllocateQuota(ledgerRepository, allocationRepository);
  const getBalance = new GetBalance(ledgerRepository);
  const getAllocationHistory = new GetAllocationHistory(ledgerRepository);
  const scopeValidator = new ScopeValidator();

  const quotaController = new QuotaController(reserveQuota, recordUsage, allocateQuota, scopeValidator);
  const balanceController = new BalanceController(getBalance, getAllocationHistory, scopeValidator);
  const healthController = new HealthController();
  const rateLimiter = createRateLimitMiddleware(new RateLimiter());

  const app = express();
  app.use(express.json());
  app.use(requestLogger);

  app.get('/health', healthController.check);

  app.post('/quota/reserve', authMiddleware, rateLimiter, asyncHandler(quotaController.reserve));
  app.post('/quota/record', authMiddleware, rateLimiter, asyncHandler(quotaController.record));
  app.post('/quota/allocate', authMiddleware, asyncHandler(quotaController.allocate));
  app.get('/quota/balance', authMiddleware, asyncHandler(balanceController.balance));
  app.get('/quota/history', authMiddleware, asyncHandler(balanceController.history));

  app.use(errorHandler);

  return app;
};
