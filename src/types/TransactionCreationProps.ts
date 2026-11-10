import type {Account} from './Account';

export type TransactionCreationProps = {
  visible: boolean;
  token: string | null;
  accounts: Account[];
  onClose: () => void;
  onCreated: () => void;
};
