export type TransactionDetailsProps = {
  transactionId: string | null;
  token: string | null;
  onClose: () => void;
  goHome: () => void;
};
