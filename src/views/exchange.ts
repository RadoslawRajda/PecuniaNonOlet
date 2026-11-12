const MAX_EXCHANGE_AMOUNT_MINOR = 9_000_000_000_000_000;
const approximateAmountFormatter = new Intl.NumberFormat('pl-PL', {minimumFractionDigits: 2, maximumFractionDigits: 2});

export function parseExchangeAmountMinor(value: string): number | null {
  const normalized = value.trim().replace(',', '.');
  if (!/^\d+(\.\d{1,2})?$/.test(normalized)) return null;
  const [whole, fraction = ''] = normalized.split('.');
  const minor = Number(whole) * 100 + Number(fraction.padEnd(2, '0'));
  return Number.isSafeInteger(minor) && minor > 0 && minor <= MAX_EXCHANGE_AMOUNT_MINOR ? minor : null;
}

export function estimateExchangeAmount(
  amount: string,
  sourceCurrency: string,
  destinationCurrency: string,
  rates: {currency_code: string; pln_per_unit: string}[],
): string | null {
  const parsed = Number(amount.trim().replace(',', '.'));
  if (!Number.isFinite(parsed) || parsed <= 0) return null;
  const sourceRate = sourceCurrency === 'PLN' ? 1 : Number(rates.find(rate => rate.currency_code === sourceCurrency)?.pln_per_unit);
  const destinationRate = destinationCurrency === 'PLN' ? 1 : Number(rates.find(rate => rate.currency_code === destinationCurrency)?.pln_per_unit);
  if (!Number.isFinite(sourceRate) || sourceRate <= 0 || !Number.isFinite(destinationRate) || destinationRate <= 0) return null;
  const estimated = parsed * sourceRate / destinationRate;
  return Number.isFinite(estimated) && estimated > 0 ? approximateAmountFormatter.format(estimated) : null;
}
