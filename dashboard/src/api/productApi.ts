// dashboard/src/api/productApi.ts
//
// Product-tab API calls. Talks to the Java backend only (never Python directly). Reuses ApiRequestError from client.ts; the tiny
// request helper is repeated here on purpose so the existing client.ts (used by the Live/Benchmark views) stays untouched.

import { ApiRequestError } from './client';
import type { ApiError } from '../types/contracts';
import type { ProductSessionStatus, ProductSpeedMultiplier, ProductStartAck } from '../types/product';

const BASE_URL = 'http://localhost:8080';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${BASE_URL}${path}`, { headers: { 'Content-Type': 'application/json' }, ...init });
  } catch (e) {
    throw new ApiRequestError(0, null, `Backend unreachable at ${BASE_URL}: ${(e as Error).message}`);
  }
  const text = await res.text();
  const body = text ? JSON.parse(text) : null;
  if (!res.ok) {
    const apiError = body as ApiError | null;
    throw new ApiRequestError(res.status, apiError, apiError?.message ?? `Request failed with status ${res.status}`);
  }
  return body as T;
}

export function fetchProductSession(): Promise<ProductSessionStatus> {
  return request<ProductSessionStatus>('/api/product/session');
}

export function startProductSession(seed: number, speedMultiplier: ProductSpeedMultiplier, robotCount = 5): Promise<ProductStartAck> {
  return request<ProductStartAck>('/api/product/session/start', {
    method: 'POST',
    body: JSON.stringify({ seed, speed: 'LIVE', config: { robotCount, speedMultiplier } }),
  });
}

export function stopProductSession(): Promise<{ message: string }> {
  return request<{ message: string }>('/api/product/session/stop', { method: 'POST' });
}

/** POST /api/product/robot/{robotId}/fix — "Mark as fixed" for a broken-down robot (400 if it is not broken down). */
export function fixProductRobot(robotId: string): Promise<{ robotId: string; message: string }> {
  return request<{ robotId: string; message: string }>(`/api/product/robot/${encodeURIComponent(robotId)}/fix`, { method: 'POST' });
}
