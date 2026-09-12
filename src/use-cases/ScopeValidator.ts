import { ScopeAccessError } from '../shared/errors.js';
import type { Scope, TenantId, UserId } from '../shared/types.js';

export type Role = 'platform_admin' | 'tenant_admin' | 'user';

/** The identity and role extracted from a verified JWT (see frameworks/auth.ts). */
export interface Principal {
  readonly role: Role;
  readonly tenantId?: TenantId;
  readonly userId?: UserId;
}

/**
 * Enforces who may act on which scope: a platform admin may touch any
 * tenant; a tenant admin may touch their own tenant and any user within it;
 * a plain user may only touch their own scope. This runs before any quota
 * operation so a caller can never read or mutate another tenant's ledger.
 */
export class ScopeValidator {
  assertCanAccess(principal: Principal, requested: Scope): void {
    if (principal.role === 'platform_admin') {
      return;
    }

    if (!principal.tenantId || principal.tenantId !== requested.tenantId) {
      throw new ScopeAccessError('Principal does not have access to this tenant');
    }

    if (principal.role === 'tenant_admin') {
      return;
    }

    // role === 'user': may only ever act on their own userId.
    if (!requested.userId || principal.userId !== requested.userId) {
      throw new ScopeAccessError('Principal does not have access to this user scope');
    }
  }
}
