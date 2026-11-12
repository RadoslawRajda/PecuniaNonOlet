import React from 'react';
import {Text, TextInput} from 'react-native';
import ReactTestRenderer from 'react-test-renderer';
import {ExchangeRatesScreen} from '../src/views/screens/ExchangeRatesScreen';
import {AppPreferencesProvider} from '../src/context/AppPreferences';

jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {getItem: jest.fn(async () => null), setItem: jest.fn(async () => undefined), removeItem: jest.fn(async () => undefined)},
}));
jest.mock('react-native-permissions', () => ({
  PERMISSIONS: {IOS: {LOCATION_WHEN_IN_USE: 'ios.permission.LOCATION_WHEN_IN_USE'}, ANDROID: {ACCESS_COARSE_LOCATION: 'android.permission.ACCESS_COARSE_LOCATION'}},
  RESULTS: {GRANTED: 'granted', DENIED: 'denied', BLOCKED: 'blocked', UNAVAILABLE: 'unavailable'},
  check: jest.fn(async () => 'granted'), request: jest.fn(async () => 'granted'),
}));
jest.mock('react-native-geolocation-service', () => ({__esModule: true, default: {getCurrentPosition: jest.fn()}}));
jest.mock('react-native-webview', () => ({WebView: () => null}));
jest.mock('react-native-safe-area-context', () => ({SafeAreaProvider: ({children}: {children: React.ReactNode}) => children, SafeAreaView: ({children}: {children: React.ReactNode}) => children, useSafeAreaInsets: () => ({top: 0, right: 0, bottom: 0, left: 0})}));

const accounts = [
  {id: 1, currency_code: 'PLN', balance: '100.00'},
  {id: 2, currency_code: 'EUR', balance: '0.00'},
];
const quote = {
  quote_id: '2b111111-1111-4111-8111-111111111111', source_amount: '4.24', destination_amount: '1.00',
  source_currency_code: 'PLN', destination_currency_code: 'EUR', exchange_rate: '0.2358490566',
  provider: 'NBP Table A', effective_date: '2026-11-11', expires_at: '2026-11-11T18:30:00Z',
};

function textContent(renderer: ReactTestRenderer.ReactTestRenderer) {
  return renderer.root.findAllByType(Text).map(node => String(node.props.children));
}

function pressButton(renderer: ReactTestRenderer.ReactTestRenderer, title: string) {
  const label = renderer.root.findAllByType(Text).find(node => String(node.props.children) === title);
  const button = label?.parent;
  if (!button?.props.onClick) throw new Error(`Button not found: ${title}`);
  return () => button.props.onClick({nativeEvent: {target: 1}, preventDefault: () => undefined, stopPropagation: () => undefined});
}

describe('exchange quote screen flow', () => {
  it('gets a quote, then discards it when the user changes the amount', async () => {
    const fetchMock = jest.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes('/api/profile/photo')) return {status: 404, ok: false, json: async () => null} as unknown as Response;
      if (url.includes('/api/accounts')) return {status: 200, ok: true, json: async () => ({accounts})} as unknown as Response;
      if (url.includes('/api/exchange-rates')) return {status: 200, ok: true, json: async () => ({provider: 'NBP Table A', effective_date: '2026-11-11', rates: [{currency_code: 'EUR', pln_per_unit: '4.24'}]})} as unknown as Response;
      if (url.includes('/api/exchange/quote')) return {status: 200, ok: true, json: async () => quote} as unknown as Response;
      throw new Error(`Unexpected API request: ${url}`);
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    let renderer!: ReactTestRenderer.ReactTestRenderer;
    await ReactTestRenderer.act(async () => {
      renderer = ReactTestRenderer.create(
        <AppPreferencesProvider token="test-token">
          <ExchangeRatesScreen token="test-token" goHome={() => undefined} />
        </AppPreferencesProvider>,
      );
      await new Promise<void>(resolve => setTimeout(resolve, 10));
    });

    await ReactTestRenderer.act(async () => {
      renderer.root.findByType(TextInput).props.onChangeText('4,24');
    });
    expect(textContent(renderer)).toContain('Orientacyjnie otrzymasz około 1,00 EUR. Dokładną kwotę pokaże wycena.');
    await ReactTestRenderer.act(async () => {
      pressButton(renderer, 'Pobierz wycenę')();
      await new Promise<void>(resolve => setTimeout(resolve, 10));
    });
    expect(textContent(renderer)).toContain('Potwierdź wymianę');
    expect(textContent(renderer)).toContain('Otrzymasz');

    await ReactTestRenderer.act(async () => {
      pressButton(renderer, 'Wróć i zmień dane')();
    });
    await ReactTestRenderer.act(async () => {
      renderer.root.findByType(TextInput).props.onChangeText('8,48');
    });
    expect(textContent(renderer)).toContain('Przygotuj wymianę');
    expect(textContent(renderer)).not.toContain('Potwierdź wymianę');
    expect(textContent(renderer)).toContain('Orientacyjnie otrzymasz około 2,00 EUR. Dokładną kwotę pokaże wycena.');
    const quoteRequest = fetchMock.mock.calls.find(([url]) => String(url).includes('/api/exchange/quote'));
    expect(quoteRequest).toBeDefined();
  });
});
