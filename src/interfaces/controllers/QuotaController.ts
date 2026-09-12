import type { Request, Response } from 'express';
import type { AllocateQuota } from '../../use-cases/AllocateQuota.js';
import type { RecordUsage } from '../../use-cases/RecordUsage.js';
import type { ReserveQuota } from '../../use-cases/ReserveQuota.js';
import type { ScopeValidator } from '../../use-cases/ScopeValidator.js';
import { asTenantId, asUserId } from '../../shared/types.js';
import { allocateRequestSchema, recordUsageRequestSchema, reserveQuotaRequestSchema } from '../../shared/validators.js';
import type { AuthenticatedRequest } from '../middleware/auth.js';

/** API surface for the two-phase enforcement model plus hierarchical allocation. */
export class QuotaController {
  constructor(
    private readonly reserveQuota: ReserveQuota,
    private readonly recordUsage: RecordUsage,
    private readonly allocateQuota: AllocateQuota,
    private readonly scopeValidator: ScopeValidator
  ) {}

  /** POST /quota/reserve — coarse pre-flight gate: can this operation start? */
  reserve = async (req: Request, res: Response): Promise<void> => {
    const body = reserveQuotaRequestSchema.parse(req.body);
    const tenantId = asTenantId(body.tenantId);
    const userId = asUserId(body.userId);
    this.scopeValidator.assertCanAccess((req as AuthenticatedRequest).principal, { tenantId, userId });

    await this.reserveQuota.execute({ tenantId, userId, resourceType: body.resourceType });
    res.json({ ok: true });
  };

  /** POST /quota/record — precise post-hoc recording of actual cost. */
  record = async (req: Request, res: Response): Promise<void> => {
    const body = recordUsageRequestSchema.parse(req.body);
    const tenantId = asTenantId(body.tenantId);
    const userId = asUserId(body.userId);
    this.scopeValidator.assertCanAccess((req as AuthenticatedRequest).principal, { tenantId, userId });

    const result = await this.recordUsage.execute({
      tenantId,
      userId,
      resourceType: body.resourceType,
      amount: body.amount,
      reason: body.reason,
    });
    res.json({ recordedAmount: result.recordedAmount, balanceAfter: result.balanceAfter });
  };

  /** POST /quota/allocate — commit budget from platform to tenant, or tenant to user. */
  allocate = async (req: Request, res: Response): Promise<void> => {
    const body = allocateRequestSchema.parse(req.body);
    const tenantId = asTenantId(body.tenantId);
    const userId = body.userId ? asUserId(body.userId) : undefined;
    this.scopeValidator.assertCanAccess((req as AuthenticatedRequest).principal, { tenantId, userId });

    const allocation = await this.allocateQuota.execute({
      tenantId,
      userId,
      resourceType: body.resourceType,
      amount: body.amount,
      reason: body.reason,
    });
    res.json({ allocation });
  };
}
