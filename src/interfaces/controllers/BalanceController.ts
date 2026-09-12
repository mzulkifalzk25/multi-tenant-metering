import type { Request, Response } from 'express';
import type { GetAllocationHistory } from '../../use-cases/GetAllocationHistory.js';
import type { GetBalance } from '../../use-cases/GetBalance.js';
import type { ScopeValidator } from '../../use-cases/ScopeValidator.js';
import { asTenantId, asUserId, RESOURCE_TYPES, type ResourceType } from '../../shared/types.js';
import { ValidationError } from '../../shared/errors.js';
import type { AuthenticatedRequest } from '../middleware/auth.js';

const parseResourceType = (value: unknown): ResourceType => {
  if (typeof value !== 'string' || !(RESOURCE_TYPES as readonly string[]).includes(value)) {
    throw new ValidationError(`resourceType must be one of ${RESOURCE_TYPES.join(', ')}`);
  }
  return value as ResourceType;
};

/** Reporting endpoints: current balance and the full ledger history behind it. */
export class BalanceController {
  constructor(
    private readonly getBalance: GetBalance,
    private readonly getAllocationHistory: GetAllocationHistory,
    private readonly scopeValidator: ScopeValidator
  ) {}

  /** GET /quota/balance?tenantId=&userId=&resourceType= */
  balance = async (req: Request, res: Response): Promise<void> => {
    const tenantId = asTenantId(String(req.query['tenantId'] ?? ''));
    const userId = asUserId(String(req.query['userId'] ?? ''));
    const resourceType = parseResourceType(req.query['resourceType']);
    this.scopeValidator.assertCanAccess((req as AuthenticatedRequest).principal, { tenantId, userId });

    const balance = await this.getBalance.execute({ tenantId, userId, resourceType });
    res.json({ balance });
  };

  /** GET /quota/history?tenantId=&userId=&resourceType= — dispute-resolution view. */
  history = async (req: Request, res: Response): Promise<void> => {
    const tenantId = asTenantId(String(req.query['tenantId'] ?? ''));
    const rawUserId = req.query['userId'];
    const resourceType = parseResourceType(req.query['resourceType']);

    if (rawUserId) {
      const userId = asUserId(String(rawUserId));
      this.scopeValidator.assertCanAccess((req as AuthenticatedRequest).principal, { tenantId, userId });
      const entries = await this.getBalance.getHistory({ tenantId, userId, resourceType });
      res.json({ entries });
      return;
    }

    this.scopeValidator.assertCanAccess((req as AuthenticatedRequest).principal, { tenantId });
    const entries = await this.getAllocationHistory.execute({ tenantId, resourceType });
    res.json({ entries });
  };
}
