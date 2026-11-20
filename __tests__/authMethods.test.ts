import {Passkey} from 'react-native-passkey';

import {buildGoogleAuthorizationOptions, signInWithPasskey} from '../src/auth/authMethods';

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
      useNonce: false,
      scopes: ['openid', 'email', 'profile'],
      additionalParameters: {nonce, prompt: 'select_account'},
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

    expect(passkeyGetMock).toHaveBeenCalledWith(options);
    expect(fetchMock).toHaveBeenNthCalledWith(2,
      'https://pecunianonolet.local:8000/api/passkeys/authentication/verify',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({credential}),
      }),
    );
  });
});
