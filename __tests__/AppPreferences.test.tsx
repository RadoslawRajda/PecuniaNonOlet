import React from 'react';
import {Text} from 'react-native';
import ReactTestRenderer from 'react-test-renderer';
import {AppPreferencesProvider, useAppPreferences} from '../src/context/AppPreferences';
import {check, request, RESULTS} from 'react-native-permissions';
import Geolocation from 'react-native-geolocation-service';

jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {getItem: jest.fn(async (key: string) => key === '@app_location_currency_enabled' ? 'true' : null), setItem: jest.fn(async () => undefined), removeItem: jest.fn(async () => undefined)},
}));
jest.mock('react-native-geolocation-service', () => ({__esModule: true, default: {getCurrentPosition: jest.fn()}}));
jest.mock('react-native-permissions', () => ({
  PERMISSIONS: {IOS: {LOCATION_WHEN_IN_USE: 'ios.permission.LOCATION_WHEN_IN_USE'}, ANDROID: {ACCESS_COARSE_LOCATION: 'android.permission.ACCESS_COARSE_LOCATION'}},
  RESULTS: {GRANTED: 'granted', DENIED: 'denied', BLOCKED: 'blocked', UNAVAILABLE: 'unavailable'},
  check: jest.fn(), request: jest.fn(),
}));

function LocationState() {
  const preferences = useAppPreferences();
  return <Text>{JSON.stringify({status: preferences.locationPermissionStatus, error: preferences.locationError, enabled: preferences.locationCurrencyEnabled, detected: preferences.locationDetectedCurrency})}</Text>;
}

async function renderState() {
  let renderer!: ReactTestRenderer.ReactTestRenderer;
  await ReactTestRenderer.act(async () => {
    renderer = ReactTestRenderer.create(<AppPreferencesProvider token="test-token"><LocationState /></AppPreferencesProvider>);
    await new Promise<void>(resolve => setTimeout(resolve, 10));
  });
  return renderer;
}

function readState(renderer: ReactTestRenderer.ReactTestRenderer) {
  return JSON.parse(renderer.root.findByType(Text).props.children as string) as {status: string; error: string | null; enabled: boolean};
}

beforeEach(() => {
  jest.clearAllMocks();
  globalThis.fetch = jest.fn(async (input: RequestInfo | URL) => String(input).includes('/api/profile/photo')
    ? ({status: 404, ok: false, blob: async () => null} as unknown as Response)
    : ({status: 200, ok: true, json: async () => ({countryCode: 'PL'})} as unknown as Response));
});

describe('location permission handling', () => {
  it('requests location and applies the detected currency after permission is granted', async () => {
    (check as jest.Mock).mockResolvedValue(RESULTS.DENIED);
    (request as jest.Mock).mockResolvedValue(RESULTS.GRANTED);
    (Geolocation.getCurrentPosition as jest.Mock).mockImplementation((resolve: (position: unknown) => void) => resolve({coords: {latitude: 52.2, longitude: 21.0}}));
    const renderer = await renderState();
    expect(readState(renderer)).toMatchObject({status: 'GRANTED', enabled: true, detected: 'PLN'});
    expect(request).toHaveBeenCalledTimes(1);
  });

  it('distinguishes a user denial and restores manual currency', async () => {
    (check as jest.Mock).mockResolvedValue(RESULTS.DENIED);
    (request as jest.Mock).mockResolvedValue(RESULTS.DENIED);
    const renderer = await renderState();
    expect(readState(renderer)).toMatchObject({status: 'DENIED', enabled: false});
    expect(readState(renderer).error).toContain('Nie przyznano dostępu');
  });

  it('keeps a blocked permission enabled so the profile can link to system settings', async () => {
    (check as jest.Mock).mockResolvedValue(RESULTS.BLOCKED);
    const renderer = await renderState();
    expect(readState(renderer)).toMatchObject({status: 'BLOCKED', enabled: true});
    expect(readState(renderer).error).toContain('ustawieniach systemu');
    expect(request).not.toHaveBeenCalled();
  });

  it('reports unavailable location without describing it as a denial', async () => {
    (check as jest.Mock).mockResolvedValue(RESULTS.UNAVAILABLE);
    const renderer = await renderState();
    expect(readState(renderer)).toMatchObject({status: 'UNAVAILABLE', enabled: true});
    expect(readState(renderer).error).toContain('niedostępna');
  });

  it('reports technical permission errors separately from user denial', async () => {
    jest.spyOn(console, 'warn').mockImplementation(() => undefined);
    (check as jest.Mock).mockRejectedValue(new Error('native error'));
    const renderer = await renderState();
    expect(readState(renderer)).toMatchObject({status: 'ERROR', enabled: true});
    expect(readState(renderer).error).toContain('Nie udało się ustalić waluty');
    expect(readState(renderer).error).not.toContain('odmów');
  });
});
