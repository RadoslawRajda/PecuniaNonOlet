import {formatExchangeRate, formatExchangeRateLabel} from '../src/views/formatters';

describe('exchange rate formatting', () => {
  it('formats rates with two Polish decimal places', () => {
    expect(formatExchangeRate('4.270000000000000000')).toBe('4,27');
    expect(formatExchangeRate(1)).toBe('1,00');
  });

  it('formats a readable currency pair', () => {
    expect(formatExchangeRateLabel('EUR', '4.27', 'PLN')).toBe('1 EUR = 4,27 PLN');
  });

  it('handles invalid rate values', () => {
    expect(formatExchangeRate('NaN')).toBe('—');
    expect(formatExchangeRate(0)).toBe('—');
  });
});
