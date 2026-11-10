export type Transaction = {
  id: string;
  type: string;
  direction: string;
  currency_code: string;
  amount: string;
  counterparty_email?: string | null;
  created_at: string;
};
