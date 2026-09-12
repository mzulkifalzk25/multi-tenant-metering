import jwt from 'jsonwebtoken';
import type { Role } from '../use-cases/ScopeValidator.js';

export interface QuotaTokenPayload {
  readonly role: Role;
  readonly tenantId?: string;
  readonly userId?: string;
}

const getSecret = (): string => {
  const secret = process.env['JWT_SECRET'];
  if (!secret) {
    throw new Error('JWT_SECRET is not configured');
  }
  return secret;
};

export const signToken = (payload: QuotaTokenPayload, expiresInSeconds = 3600): string =>
  jwt.sign(payload, getSecret(), { expiresIn: expiresInSeconds });

/** Verifies a bearer token and returns its payload, or throws jwt's own error on failure/expiry. */
export const verifyToken = (token: string): QuotaTokenPayload => {
  const decoded = jwt.verify(token, getSecret());
  if (typeof decoded === 'string') {
    throw new Error('Unexpected string JWT payload');
  }
  return decoded as unknown as QuotaTokenPayload;
};
