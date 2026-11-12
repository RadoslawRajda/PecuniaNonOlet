import type {Account} from './Account';
import type {TransactionCreationFormValues} from './TransactionCreationFormValues';

export type TransactionCreationProps = {
  visible: boolean;
  token: string | null;
  accounts: Account[];
  initialValues?: TransactionCreationFormValues | null;
  onClose: () => void;
  onCreated: (transactionId?: string) => void;
};
