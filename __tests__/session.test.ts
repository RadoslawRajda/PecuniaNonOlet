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

  it.each([429, 503])('keeps a usable refresh token after transient HTTP %i', async status => {
    await saveSessionTokens(initialPair);
    let refreshRequests = 0;
    globalThis.fetch = jest.fn(async input => {
      if (String(input).endsWith('/api/refresh')) {
        refreshRequests += 1;
        return new Response(null, {status, headers: {'Retry-After': '3'}});
      }
      return new Response(null, {status: 401});
    }) as typeof fetch;

    await expect(authenticatedFetch('https://api.local/resource')).rejects.toThrow('chwilowo niedostępne');
    await expect(authenticatedFetch('https://api.local/resource')).rejects.toThrow('chwilowo niedostępne');
    expect(refreshRequests).toBe(1);
    expect(keychain.resetGenericPassword).not.toHaveBeenCalled();
    expect(await loadSessionTokens()).toEqual(initialPair);
  });

  it('keeps the session after a refresh network error', async () => {
    await saveSessionTokens(initialPair);
    globalThis.fetch = jest.fn(async input => {
      if (String(input).endsWith('/api/refresh')) throw new Error('offline');
      return new Response(null, {status: 401});
    }) as typeof fetch;

    await expect(authenticatedFetch('https://api.local/resource')).rejects.toThrow('Nie udało się połączyć');
    expect(keychain.resetGenericPassword).not.toHaveBeenCalled();
    expect(await loadSessionTokens()).toEqual(initialPair);
  });

  it('keeps the session when refresh times out', async () => {
    await saveSessionTokens(initialPair);
    globalThis.fetch = jest.fn(async (input, init) => {
      if (!String(input).endsWith('/api/refresh')) return new Response(null, {status: 401});
      return new Promise<Response>((_, reject) => {
        init?.signal?.addEventListener('abort', () => reject(new Error('aborted')));
      });
    }) as typeof fetch;

    jest.useFakeTimers();
    try {
      const request = authenticatedFetch('https://api.local/resource');
      const outcome = request.then(() => null, error => error);
      await jest.advanceTimersByTimeAsync(10_000);
      expect(await outcome).toEqual(expect.objectContaining({message: expect.stringContaining('Nie udało się połączyć')}));
      expect(keychain.resetGenericPassword).not.toHaveBeenCalled();
      expect(await loadSessionTokens()).toEqual(initialPair);
    } finally {
      jest.useRealTimers();
    }
  });

  it('ends the local session after confirmed refresh rejection or malformed success', async () => {
    for (const refreshResponse of [
      new Response(null, {status: 401}),
      new Response(JSON.stringify({access_token: 'invalid'}), {status: 200}),
    ]) {
      await saveSessionTokens(initialPair);
      globalThis.fetch = jest.fn(async input => String(input).endsWith('/api/refresh')
        ? refreshResponse
        : new Response(null, {status: 401})) as typeof fetch;
      expect((await authenticatedFetch('https://api.local/resource')).status).toBe(401);
      expect(await loadSessionTokens()).toBeNull();
    }
  });

  it('recovers the persistence queue after one Keychain write failure', async () => {
    (keychain.setGenericPassword as jest.Mock).mockRejectedValueOnce(new Error('Keychain unavailable'));
    await expect(saveSessionTokens(initialPair)).rejects.toThrow('Keychain unavailable');
    await saveSessionTokens(rotatedPair);
    expect(await loadSessionTokens()).toEqual(rotatedPair);
    await clearSessionTokens();
    expect(await loadSessionTokens()).toBeNull();
  });

  it('does not restore a logged-out session from a late refresh response', async () => {
    await saveSessionTokens(initialPair);
    let finishRefresh: ((response: Response) => void) | undefined;
    globalThis.fetch = jest.fn(async input => {
      if (String(input).endsWith('/api/refresh')) {
        return new Promise<Response>(resolve => { finishRefresh = resolve; });
      }
      return new Response(null, {status: 401});
    }) as typeof fetch;
    const request = authenticatedFetch('https://api.local/resource');
    await Promise.resolve();
    await Promise.resolve();
    expect(finishRefresh).toBeDefined();
    await clearSessionTokens();
    finishRefresh!(new Response(JSON.stringify(rotatedPair), {status: 200}));
    expect((await request).status).toBe(401);
    expect(await loadSessionTokens()).toBeNull();
  });

  it('does not overwrite a different account with a late refresh response', async () => {
    await saveSessionTokens(initialPair);
    let finishRefresh: ((response: Response) => void) | undefined;
    globalThis.fetch = jest.fn(async (input, init) => {
      if (String(input).endsWith('/api/refresh')) {
        return new Promise<Response>(resolve => { finishRefresh = resolve; });
      }
      if (String(input).endsWith('/new-account')) {
        expect(new Headers(init?.headers).get('Authorization')).toBe(`Bearer ${rotatedPair.access_token}`);
        return new Response('{}', {status: 200});
      }
      return new Response(null, {status: 401});
    }) as typeof fetch;
    const oldRequest = authenticatedFetch('https://api.local/old-account');
    await Promise.resolve();
    await Promise.resolve();
    expect(finishRefresh).toBeDefined();
    await saveSessionTokens(rotatedPair);
    finishRefresh!(new Response(JSON.stringify(initialPair), {status: 200}));
    expect((await oldRequest).status).toBe(401);
    expect((await authenticatedFetch('https://api.local/new-account')).status).toBe(200);
    expect(await loadSessionTokens()).toEqual(rotatedPair);
  });
});
