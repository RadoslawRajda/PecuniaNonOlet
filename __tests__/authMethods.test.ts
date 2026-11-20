import {Passkey} from 'react-native-passkey';
import {authorize} from 'react-native-app-auth';

import {
  buildGoogleAuthorizationOptions,
  changePassword,
  getApiErrorMessage,
  reauthenticateWithGoogle,
  signInWithPasskey,
} from '../src/auth/authMethods';
import {authenticatedFetch, saveSessionTokens} from '../src/auth/session';

jest.mock('../src/auth/session', () => ({authenticatedFetch: jest.fn(), saveSessionTokens: jest.fn()}));

const passkeyGetMock = Passkey.get as jest.Mock;

describe('native authentication methods', () => {
  const originalFetch = globalThis.fetch;

  afterEach(() => {
    globalThis.fetch = originalFetch;
    jest.clearAllMocks();
  });

  it('builds the Google AppAuth request with PKCE, state-managed nonce, and the native redirect scheme', () => {
    const nonce = 'server-issued-one-time-nonce';
    expect(buildGoogleAuthorizationOptions('ios-client.apps.googleusercontent.com', nonce)).toEqual({
      issuer: 'https://accounts.google.com',
      clientId: 'ios-client.apps.googleusercontent.com',
      redirectUrl: 'com.googleusercontent.apps.ios-client:/oauth2redirect/google',
      usePKCE: true,
      useNonce: true,
      scopes: ['openid', 'email', 'profile'],
      additionalParameters: {
        nonce,
        prompt: 'select_account',
        claims: JSON.stringify({id_token: {auth_time: {essential: true}}}),
      },
    });
  });

  it('gets passkey options and submits the native assertion to the API', async () => {
    const options = {challenge: 'server-challenge'};
    const credential = {id: 'credential-id', response: {signature: 'signature'}};
    const fetchMock = jest.fn()
      .mockResolvedValueOnce({ok: true, json: async () => options})
      .mockResolvedValueOnce({ok: true, json: async () => ({token: 'app-session'})});
    globalThis.fetch = fetchMock as typeof fetch;
    passkeyGetMock.mockResolvedValue(credential);

    await signInWithPasskey();

    expect(fetchMock).toHaveBeenNthCalledWith(
      1,
      expect.stringContaining('/api/passkeys/authentication/options'),
      expect.objectContaining({method: 'POST'}),
    );
    expect(passkeyGetMock).toHaveBeenCalledWith(options);
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      expect.stringContaining('/api/passkeys/authentication/verify'),
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({credential}),
      }),
    );
  });

  it('binds a fresh Google ceremony to the current backend session', async () => {
    const authenticatedFetchMock = authenticatedFetch as jest.Mock;
    authenticatedFetchMock
      .mockResolvedValueOnce({ok: true, json: async () => ({nonce: 'server-nonce'})})
      .mockResolvedValueOnce({ok: true, json: async () => ({access_token: 'new-access', refresh_token: 'new-refresh'})});
    (authorize as jest.Mock).mockResolvedValue({idToken: 'signed-google-id-token'});

    await reauthenticateWithGoogle('current-access-token');

    expect(authenticatedFetchMock).toHaveBeenNthCalledWith(
      1, expect.stringContaining('/api/auth/google/reauth/nonce'),
      expect.objectContaining({method: 'POST', accessToken: 'current-access-token'}),
    );
    expect(saveSessionTokens).toHaveBeenCalledWith({access_token: 'new-access', refresh_token: 'new-refresh'});
    expect(authorize).toHaveBeenCalledWith(expect.objectContaining({
      additionalParameters: expect.objectContaining({
        nonce: 'server-nonce',
        prompt: 'select_account',
      }),
    }));
    expect(authenticatedFetchMock).toHaveBeenNthCalledWith(
      2, expect.stringContaining('/api/auth/google/reauth'),
      expect.objectContaining({
        method: 'POST', accessToken: 'current-access-token',
        body: JSON.stringify({id_token: 'signed-google-id-token', nonce: 'server-nonce'}),
      }),
    );
  });

  it('sends the password-change proof only in an authenticated JSON body', async () => {
    const authenticatedFetchMock = authenticatedFetch as jest.Mock;
    authenticatedFetchMock.mockResolvedValueOnce({ok: true, json: async () => ({})});

    await changePassword('current-access-token', {
      current_password: 'current-password',
      new_password: 'new-password',
      mfa_code: '123456',
    });

    expect(authenticatedFetchMock).toHaveBeenCalledWith(
      expect.stringContaining('/api/change-password'),
      expect.objectContaining({
        method: 'POST',
        accessToken: 'current-access-token',
        body: JSON.stringify({
          current_password: 'current-password',
          new_password: 'new-password',
          mfa_code: '123456',
        }),
      }),
    );
  });

  it('renders FastAPI validation errors as text instead of an object', async () => {
    const authenticatedFetchMock = authenticatedFetch as jest.Mock;
    authenticatedFetchMock.mockResolvedValueOnce({
      ok: false,
      status: 422,
      json: async () => ({
        detail: [{msg: 'Hasło jest zbyt popularne lub znajduje się na liście haseł wyciekłych.'}],
      }),
    });

    await expect(changePassword('current-access-token', {
      current_password: 'current-password',
      new_password: 'password123',
    })).rejects.toThrow('Hasło jest zbyt popularne lub znajduje się na liście haseł wyciekłych.');
  });

  it('uses a safe fallback for malformed API errors', () => {
    expect(getApiErrorMessage([{unexpected: true}], 'Nie udało się zapisać danych.'))
      .toBe('Nie udało się zapisać danych.');
  });
});
