import pinoHttp from 'pino-http';
import { logger } from '../../shared/logger.js';

/** Structured per-request logging via pino-http, reusing the shared pino instance. */
export const requestLogger = pinoHttp({ logger });
