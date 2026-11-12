export type Transaction = {
  id: string;
  type: string;
  direction: string;
  currency_code: string;
  amount: string;
  destination_currency_code?: string | null;
  destination_amount?: string | null;
  counterparty_email?: string | null;
  created_at: string;
};
