import type {Account} from './Account';

export type TransactionCreationFormValues = {
  recipientEmail: string;
  account: Account | null;
  amount: string;
};
