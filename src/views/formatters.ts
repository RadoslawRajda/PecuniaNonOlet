const exchangeRateFormatter = new Intl.NumberFormat('pl-PL', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

export function formatExchangeRate(value: string | number): string {
  const parsed = typeof value === 'number' ? value : Number(value);
  return Number.isFinite(parsed) && parsed > 0 ? exchangeRateFormatter.format(parsed) : '—';
}

export function formatExchangeRateLabel(
  sourceCurrency: string,
  rate: string | number,
  destinationCurrency: string,
): string {
  return `1 ${sourceCurrency} = ${formatExchangeRate(rate)} ${destinationCurrency}`;
}
