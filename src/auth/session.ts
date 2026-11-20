import * as Keychain from 'react-native-keychain';
import {API_URL} from '@env';

type TokenPair = {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  refresh_expires_in: number;
};

type AuthenticatedRequestInit = RequestInit & {accessToken?: string | null};

const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
const STORAGE_SERVICE = '@app_auth_token';
const REFRESH_TIMEOUT_MS = 10_000;
const MAX_REFRESH_BACKOFF_MS = 60_000;
const KEYCHAIN_OPTIONS = {
  service: STORAGE_SERVICE,
  accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

let currentTokens: TokenPair | null = null;
let currentFamily = 0;
let refreshInFlight: Promise<TokenPair | null> | null = null;
let refreshInFlightFamily = -1;
let persistenceInFlight: Promise<void> = Promise.resolve();
let refreshRetryAt = 0;
const accessTokenListeners = new Set<(token: string | null) => void>();

function refreshBackoffMs(header: string | null): number {
  if (!header) return 1000;
  const seconds = /^\d+$/.test(header) ? Number(header) : (Date.parse(header) - Date.now()) / 1000;
  if (!Number.isFinite(seconds)) return 1000;
  return Math.min(Math.max(Math.ceil(seconds) * 1000, 1000), MAX_REFRESH_BACKOFF_MS);
}

function isTokenPair(value: unknown): value is TokenPair {
  if (!value || typeof value !== 'object') return false;
  const pair = value as Partial<TokenPair>;
  return typeof pair.access_token === 'string'
    && /^[A-Za-z0-9_-]{43}$/.test(pair.access_token)
    && typeof pair.refresh_token === 'string'
    && /^[A-Za-z0-9_-]{43}$/.test(pair.refresh_token)
    && typeof pair.expires_in === 'number'
    && Number.isSafeInteger(pair.expires_in)
    && pair.expires_in > 0
    && typeof pair.refresh_expires_in === 'number'
    && Number.isSafeInteger(pair.refresh_expires_in)
    && pair.refresh_expires_in > 0;
}

function publishAccessToken(token: string | null) {
  for (const listener of accessTokenListeners) listener(token);
}

function persistTokens(tokens: TokenPair | null): Promise<void> {
  const operation = persistenceInFlight.catch(() => undefined).then(async () => {
    if (tokens) {
      await Keychain.setGenericPassword('app-auth-session', JSON.stringify(tokens), KEYCHAIN_OPTIONS);
    } else {
      await Keychain.resetGenericPassword(KEYCHAIN_OPTIONS);
    }
  });
  persistenceInFlight = operation.catch(() => undefined);
  return operation;
}

export async function saveSessionTokens(value: unknown, preserveFamily = false): Promise<TokenPair> {
  if (!isTokenPair(value)) throw new Error('Serwer nie zwrócił poprawnej sesji.');
  const family = preserveFamily ? currentFamily : currentFamily + 1;
  if (!preserveFamily) {
    currentFamily = family;
    refreshRetryAt = 0;
  }
  try {
    await persistTokens(value);
  } catch (error) {
    if (currentFamily === family) {
      currentTokens = null;
      currentFamily += 1;
      publishAccessToken(null);
      await persistTokens(null).catch(() => undefined);
    }
    throw error;
  }
  if (currentFamily !== family) throw new Error('Sesja została zmieniona podczas zapisu.');
  currentTokens = value;
  publishAccessToken(value.access_token);
  return value;
}

export async function loadSessionTokens(): Promise<TokenPair | null> {
  const familyAtStart = currentFamily;
  const credentials = await Keychain.getGenericPassword(KEYCHAIN_OPTIONS);
  if (familyAtStart !== currentFamily) return currentTokens;
  if (!credentials) return null;
  let parsed: unknown;
  try {
    parsed = JSON.parse(credentials.password);
  } catch {
    // Migrate the previous single-token Keychain entry by clearing it. It cannot
    // be refreshed safely because older backend sessions have no refresh token.
    await clearSessionTokens();
    return null;
  }
  if (!isTokenPair(parsed)) {
    await clearSessionTokens();
    return null;
  }
  currentFamily += 1;
  currentTokens = parsed;
  publishAccessToken(parsed.access_token);
  return parsed;
}

export async function clearSessionTokens(): Promise<void> {
  currentTokens = null;
  currentFamily += 1;
  refreshRetryAt = 0;
  publishAccessToken(null);
  await persistTokens(null);
}

export function subscribeAccessToken(listener: (token: string | null) => void): () => void {
  accessTokenListeners.add(listener);
  return () => accessTokenListeners.delete(listener);
}

async function refreshTokens(): Promise<TokenPair | null> {
  if (refreshInFlight && refreshInFlightFamily === currentFamily) return refreshInFlight;
  const refreshToken = currentTokens?.refresh_token;
  if (!refreshToken) return null;
  const familyAtStart = currentFamily;

  refreshInFlight = (async () => {
    try {
      if (Date.now() < refreshRetryAt) {
        throw new Error('Odświeżanie sesji jest chwilowo niedostępne. Spróbuj ponownie później.');
      }
      let response: Response;
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), REFRESH_TIMEOUT_MS);
      try {
        response = await fetch(`${apiBaseUrl}/api/refresh`, {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({refresh_token: refreshToken}),
          signal: controller.signal,
        });
      } catch {
        refreshRetryAt = Date.now() + 1000;
        throw new Error('Nie udało się połączyć z serwerem podczas odświeżania sesji.');
      } finally {
        clearTimeout(timeout);
      }
      if (familyAtStart !== currentFamily) return null;
      if (!response.ok && ![400, 401, 403, 422].includes(response.status)) {
        refreshRetryAt = Date.now() + refreshBackoffMs(response.headers.get('Retry-After'));
        throw new Error('Odświeżanie sesji jest chwilowo niedostępne. Spróbuj ponownie później.');
      }
      if (!response.ok) {
        await clearSessionTokens();
        return null;
      }
      const data: unknown = await response.json().catch(() => null);
      if (familyAtStart !== currentFamily) return null;
      if (!isTokenPair(data)) {
        await clearSessionTokens();
        return null;
      }
      refreshRetryAt = 0;
      return await saveSessionTokens(data, true);
    } finally {
      if (refreshInFlightFamily === familyAtStart) {
        refreshInFlight = null;
        refreshInFlightFamily = -1;
      }
    }
  })();
  refreshInFlightFamily = familyAtStart;
  return refreshInFlight;
}

function withBearer(init: RequestInit, token: string): RequestInit {
  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${token}`);
  return {...init, headers};
}

export async function authenticatedFetch(
  input: RequestInfo,
  init: AuthenticatedRequestInit = {},
): Promise<Response> {
  const {accessToken: fallbackToken, ...requestInit} = init;
  const authorization = new Headers(requestInit.headers).get('Authorization');
  const headerToken = authorization?.match(/^Bearer\s+(.+)$/i)?.[1] ?? null;
  const firstToken = currentTokens?.access_token ?? fallbackToken ?? headerToken;
  if (!firstToken) throw new Error('Brak aktywnej sesji. Zaloguj się ponownie.');
  const familyAtStart = currentFamily;

  const response = await fetch(input, withBearer(requestInit, firstToken));
  if (response.status !== 401 || !currentTokens?.refresh_token) return response;
  if (familyAtStart !== currentFamily) return response;

  // Another request may already have rotated this token while this request was
  // in flight; retry with that newer token before rotating again.
  const nextPair = currentTokens.access_token !== firstToken ? currentTokens : await refreshTokens();
  if (familyAtStart !== currentFamily) return response;
  if (!nextPair) return response;
  return fetch(input, withBearer(requestInit, nextPair.access_token));
}

export async function logoutRemoteSession(): Promise<void> {
  const refreshToken = currentTokens?.refresh_token;
  if (!refreshToken) return;
  await fetch(`${apiBaseUrl}/api/logout`, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({refresh_token: refreshToken}),
  });
}
