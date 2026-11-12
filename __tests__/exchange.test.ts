import {estimateExchangeAmount, parseExchangeAmountMinor} from '../src/views/exchange';

describe('exchange amount parsing', () => {
  it('converts Polish decimal input to minor units exactly', () => {
    expect(parseExchangeAmountMinor('12,34')).toBe(1234);
    expect(parseExchangeAmountMinor('12.3')).toBe(1230);
    expect(parseExchangeAmountMinor('7')).toBe(700);
  });

  it('rejects zero, malformed input, excess precision, and values outside backend bounds', () => {
    expect(parseExchangeAmountMinor('0')).toBeNull();
    expect(parseExchangeAmountMinor('1,234')).toBeNull();
    expect(parseExchangeAmountMinor('-1')).toBeNull();
    expect(parseExchangeAmountMinor('90000000000000.01')).toBeNull();
  });
});

describe('exchange estimate', () => {
  it('uses the latest PLN rates for a display-only estimate', () => {
    const rates = [{currency_code: 'EUR', pln_per_unit: '4.24'}, {currency_code: 'USD', pln_per_unit: '4.00'}];
    expect(estimateExchangeAmount('4,24', 'PLN', 'EUR', rates)).toBe('1,00');
    expect(estimateExchangeAmount('1', 'EUR', 'USD', rates)).toBe('1,06');
  });

  it('returns no estimate when the rate table is incomplete', () => {
    expect(estimateExchangeAmount('10', 'PLN', 'EUR', [])).toBeNull();
  });
});
