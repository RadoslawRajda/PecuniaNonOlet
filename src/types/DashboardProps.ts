export type DashboardProps = {
  onLogout: () => void;
  username: string;
  token: string | null;
  onExchangeRates: () => void;
  onProfile: () => void;
  onQrScanner: () => void;
  onTransactionHistory: () => void;
  goHome: () => void;
};
