import {Platform} from 'react-native';
import {authorize, type AuthConfiguration} from 'react-native-app-auth';
import {Passkey} from 'react-native-passkey';
import {authenticatedFetch, saveSessionTokens} from './session';

import {API_URL, GOOGLE_ANDROID_CLIENT_ID, GOOGLE_IOS_CLIENT_ID} from '@env';

const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

type ValidationErrorDetail = {
  msg?: unknown;
};

/** Convert API error details into text that can be safely shown in the UI. */
export function getApiErrorMessage(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map(item => {
        if (item === null || typeof item !== 'object') return null;
        const message = (item as ValidationErrorDetail).msg;
        return typeof message === 'string' && message.trim() ? message.trim() : null;
      })
      .filter((message): message is string => Boolean(message));
    if (messages.length > 0) return [...new Set(messages)].join('\n');
  }

  return fallback;
}

const request = async (path: string, init?: RequestInit, accessToken?: string) => {
  const headers = {'Content-Type': 'application/json', ...(init?.headers ?? {})};
  const response = await (accessToken
    ? authenticatedFetch(`${apiBaseUrl}${path}`, {...init, headers, accessToken})
    : fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers,
  }));
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    throw new Error(getApiErrorMessage(data?.detail, `Błąd serwera (${response.status}).`));
  }
  return data;
};

export async function signInWithPasskey() {
  const options = await request('/api/passkeys/authentication/options', {method: 'POST'});
  const credential = await Passkey.get(options);
  return request('/api/passkeys/authentication/verify', {
    method: 'POST', body: JSON.stringify({credential}),
  });
}

export async function signInWithGoogle(linkToken?: string) {
  const {nonce} = await request(linkToken ? '/api/auth/google/link/nonce' : '/api/auth/google/nonce', {
    method: 'POST',
  }, linkToken);
  const result = await authorizeGoogle(nonce);
  const path = linkToken ? '/api/auth/google/link' : '/api/auth/google/login';
  return request(path, {
    method: 'POST',
    body: JSON.stringify({id_token: result.idToken, nonce}),
  }, linkToken);
}

export async function getGoogleConnectionStatus(
  accessToken: string,
): Promise<{linked: boolean; has_local_password: boolean}> {
  return request('/api/auth/google/status', undefined, accessToken);
}

async function authorizeGoogle(nonce: string, requireFreshAuthentication = false) {
  const clientId = Platform.OS === 'ios' ? GOOGLE_IOS_CLIENT_ID : GOOGLE_ANDROID_CLIENT_ID;
  if (!clientId) {
    throw new Error('Uzupełnij GOOGLE_IOS_CLIENT_ID i GOOGLE_ANDROID_CLIENT_ID w pliku .env.');
  }
  const configuration = requireFreshAuthentication
    ? buildGoogleReauthenticationOptions(clientId, nonce)
    : buildGoogleAuthorizationOptions(clientId, nonce);
  const result = await authorize(configuration);
  if (!result.idToken) throw new Error('Google nie zwrócił tokenu ID.');
  return result;
}

export async function reauthenticateWithGoogle(accessToken: string): Promise<void> {
  const {nonce} = await request('/api/auth/google/reauth/nonce', {method: 'POST'}, accessToken);
  const result = await authorizeGoogle(nonce, true);
  const session = await request('/api/auth/google/reauth', {
    method: 'POST',
    body: JSON.stringify({id_token: result.idToken, nonce}),
  }, accessToken);
  await saveSessionTokens(session);
}

export async function changePassword(
  accessToken: string,
  payload: {current_password?: string; new_password: string; mfa_code?: string},
): Promise<void> {
  await request('/api/change-password', {
    method: 'POST',
    body: JSON.stringify(payload),
  }, accessToken);
}

export function buildGoogleAuthorizationOptions(clientId: string, nonce: string): AuthConfiguration {
  return buildGoogleOptions(clientId, nonce, 'select_account');
}

/**
 * Build a distinct OIDC ceremony for changing credentials or managing passkeys.
 * `select_account` proves only account selection; OIDC defines `max_age=0` as
 * equivalent to `prompt=login`, so both are sent and the backend verifies the
 * signed `auth_time` claim before allowing the sensitive operation.
 */
export function buildGoogleReauthenticationOptions(
  clientId: string,
  nonce: string,
): AuthConfiguration {
  return buildGoogleOptions(clientId, nonce, 'login');
}

function buildGoogleOptions(
  clientId: string,
  nonce: string,
  prompt: 'login' | 'select_account',
): AuthConfiguration {
  const clientIdPrefix = clientId.replace(/\.apps\.googleusercontent\.com$/, '');
  return {
    issuer: 'https://accounts.google.com',
    clientId,
    redirectUrl: `com.googleusercontent.apps.${clientIdPrefix}:/oauth2redirect/google`,
    scopes: ['openid', 'email', 'profile'],
    additionalParameters: {
      nonce,
      max_age: '0',
      prompt,
      claims: JSON.stringify({id_token: {auth_time: {essential: true}}}),
    },
    usePKCE: true,
    // AppAuth passes this exact backend-issued nonce to Google only when enabled.
    // The backend verifies the nonce claim in the returned ID token before login.
    useNonce: true,
  };
}

export async function createPasskey(
  token: string,
  label = Platform.OS === 'ios' ? 'iPhone' : Platform.OS === 'android' ? 'Android' : 'Urządzenie',
) {
  const options = await request('/api/passkeys/registration/options', {method: 'POST'}, token);
  const credential = await Passkey.create(options);
  return request('/api/passkeys/registration/verify', {
    method: 'POST',
    body: JSON.stringify({credential, label}),
  }, token);
}

export async function getPasskeys(token: string) {
  return request('/api/passkeys', undefined, token);
}

export async function removePasskey(token: string, id: string) {
  return request(`/api/passkeys/${encodeURIComponent(id)}`, {
    method: 'DELETE',
  }, token);
}
