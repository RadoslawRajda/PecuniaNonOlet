export type TransactionDetailsData = {
  id: string;
  type: string;
  status: string;
  direction: string;
  currency_code: string;
  amount: string;
  source_currency_code?: string | null;
  destination_currency_code: string;
  source_amount?: string | null;
  destination_amount: string;
  exchange_rate?: string | null;
  counterparty_email?: string | null;
  created_at: string;
};
