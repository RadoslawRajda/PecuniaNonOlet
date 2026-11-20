import * as Keychain from 'react-native-keychain';
import {
  authenticatedFetch,
  clearSessionTokens,
  loadSessionTokens,
  saveSessionTokens,
} from '../src/auth/session';

const keychain = Keychain as jest.Mocked<typeof Keychain>;
const initialPair = {
  access_token: 'a'.repeat(43),
  refresh_token: 'r'.repeat(43),
  expires_in: 900,
  refresh_expires_in: 2_592_000,
};
const rotatedPair = {
  access_token: 'b'.repeat(43),
  refresh_token: 's'.repeat(43),
  expires_in: 900,
  refresh_expires_in: 2_592_000,
};

describe('opaque refresh session client', () => {
  const originalFetch = globalThis.fetch;

  beforeEach(async () => {
    await clearSessionTokens();
    jest.clearAllMocks();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
  });

  it('stores both tokens in Keychain and reloads them', async () => {
    await saveSessionTokens(initialPair);
    expect(keychain.setGenericPassword).toHaveBeenCalledWith(
      'app-auth-session',
      JSON.stringify(initialPair),
      expect.objectContaining({service: '@app_auth_token'}),
    );
    (keychain.getGenericPassword as jest.Mock).mockResolvedValueOnce({
      username: 'app-auth-session',
      password: JSON.stringify(initialPair),
      service: '@app_auth_token',
    });
    expect(await loadSessionTokens()).toEqual(initialPair);
  });

  it('rotates once for concurrent expired access-token requests and retries both', async () => {
    await saveSessionTokens(initialPair);
    let resourceRequests = 0;
    let refreshRequests = 0;
    globalThis.fetch = jest.fn(async (input, init) => {
      const url = String(input);
      if (url.endsWith('/api/refresh')) {
        refreshRequests += 1;
        expect(JSON.parse(String(init?.body))).toEqual({refresh_token: initialPair.refresh_token});
        return new Response(JSON.stringify(rotatedPair), {status: 200});
      }
      resourceRequests += 1;
      const authorization = new Headers(init?.headers).get('Authorization');
      if (resourceRequests <= 2) {
        expect(authorization).toBe(`Bearer ${initialPair.access_token}`);
        return new Response(null, {status: 401});
      }
      expect(authorization).toBe(`Bearer ${rotatedPair.access_token}`);
      return new Response('{}', {status: 200});
    }) as typeof fetch;

    const results = await Promise.all([
      authenticatedFetch('https://api.local/resource/a'),
      authenticatedFetch('https://api.local/resource/b'),
    ]);

    expect(results.map(result => result.status)).toEqual([200, 200]);
    expect(refreshRequests).toBe(1);
    expect(resourceRequests).toBe(4);
  });
});
