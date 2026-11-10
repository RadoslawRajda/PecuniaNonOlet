export type DashboardProps = {
  onLogout: () => void;
  username: string;
  token: string | null;
  onExchangeRates: () => void;
  onProfile: () => void;
  onQrScanner: () => void;
  onQrGeneration: () => void;
  onTransactionHistory: () => void;
  goHome: () => void;
};
