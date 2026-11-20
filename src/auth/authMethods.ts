import {Platform} from 'react-native';
import {authorize} from 'react-native-app-auth';
import {Passkey} from 'react-native-passkey';

import {API_URL, GOOGLE_ANDROID_CLIENT_ID, GOOGLE_IOS_CLIENT_ID} from '@env';

const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
const request = async (path: string, init?: RequestInit) => {
  const response = await fetch(`${apiBaseUrl}${path}`, {
    ...init,
    headers: {'Content-Type': 'application/json', ...(init?.headers ?? {})},
  });
  const data = await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.detail ?? `Błąd serwera (${response.status}).`);
  return data;
};

export async function signInWithPasskey() {
  const options = await request('/api/passkeys/authentication/options');
  const credential = await Passkey.get(options);
  return request('/api/passkeys/authentication/verify', {
    method: 'POST', body: JSON.stringify({credential}),
  });
}

export async function signInWithGoogle(linkToken?: string) {
  const {nonce} = await request(linkToken ? '/api/auth/google/link/nonce' : '/api/auth/google/nonce', {
    method: 'POST', headers: linkToken ? {Authorization: `Bearer ${linkToken}`} : undefined,
  });
  const clientId = Platform.OS === 'ios' ? GOOGLE_IOS_CLIENT_ID : GOOGLE_ANDROID_CLIENT_ID;
  if (!clientId) {
    throw new Error('Uzupełnij GOOGLE_IOS_CLIENT_ID i GOOGLE_ANDROID_CLIENT_ID w pliku .env.');
  }
  const clientIdPrefix = clientId.replace(/\.apps\.googleusercontent\.com$/, '');
  const redirectUrl = `com.googleusercontent.apps.${clientIdPrefix}:/oauth2redirect/google`;
  const result = await authorize({
    issuer: 'https://accounts.google.com',
    clientId,
    redirectUrl,
    scopes: ['openid', 'email', 'profile'],
    additionalParameters: {nonce, prompt: 'select_account'},
    usePKCE: true,
    useNonce: false,
  });
  if (!result.idToken) throw new Error('Google nie zwrócił tokenu ID.');
  const path = linkToken ? '/api/auth/google/link' : '/api/auth/google/login';
  return request(path, {
    method: 'POST',
    headers: linkToken ? {Authorization: `Bearer ${linkToken}`} : undefined,
    body: JSON.stringify({id_token: result.idToken, nonce}),
  });
}

export async function createPasskey(
  token: string,
  label = Platform.OS === 'ios' ? 'iPhone' : Platform.OS === 'android' ? 'Android' : 'Urządzenie',
) {
  const options = await request('/api/passkeys/registration/options', {
    method: 'POST', headers: {Authorization: `Bearer ${token}`},
  });
  const credential = await Passkey.create(options);
  return request('/api/passkeys/registration/verify', {
    method: 'POST',
    headers: {Authorization: `Bearer ${token}`},
    body: JSON.stringify({credential, label}),
  });
}

export async function getPasskeys(token: string) {
  return request('/api/passkeys', {headers: {Authorization: `Bearer ${token}`}});
}

export async function removePasskey(token: string, id: string) {
  return request(`/api/passkeys/${encodeURIComponent(id)}`, {
    method: 'DELETE', headers: {Authorization: `Bearer ${token}`},
  });
}
