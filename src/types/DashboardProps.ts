export type DashboardProps = {
  username: string;
  token: string | null;
  goHome: () => void;
  onExchange: () => void;
  onQr: () => void;
  onHistory: () => void;
  initialTransactionId?: string | null;
  onInitialTransactionShown?: () => void;
};
