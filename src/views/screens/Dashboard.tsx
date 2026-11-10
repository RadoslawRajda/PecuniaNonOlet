import React from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {API_URL} from '@env';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';
import {TransactionDetails} from './TransactionDetails';
import {TransactionCreation} from './TransactionCreation';
import type {Account} from '../../types/Account';
import type {Transaction} from '../../types/Transaction';
import type {DashboardProps} from '../../types/DashboardProps';

export function Dashboard({
  onLogout,
  username,
  token,
  onExchangeRates,
  onProfile,
  onQrScanner,
  onTransactionHistory,
  goHome
}: DashboardProps) {
  const [accounts, setAccounts] = React.useState<Account[]>([]);
  const [transactions, setTransactions] = React.useState<Transaction[]>([]);
  const [selectedCurrency, setSelectedCurrency] = React.useState<string | null>(null);
  const [isCurrencyPickerVisible, setCurrencyPickerVisible] = React.useState(false);
  const [selectedTransactionId, setSelectedTransactionId] = React.useState<string | null>(null);
  const [isCreationVisible, setCreationVisible] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  const loadDashboardData = React.useCallback(async () => {
    if (!token) {
      setError('Brak aktywnego tokenu. Zaloguj się ponownie.');
      setIsLoading(false);
      goHome();
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const headers = {Authorization: `Bearer ${token}`};
      const [accountsResponse, transactionsResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/accounts`, {headers}),
        fetch(`${apiBaseUrl}/api/transactions?limit=10`, {headers}),
      ]);

      const accountsData = await accountsResponse.json().catch(() => null);
      const transactionsData = await transactionsResponse.json().catch(() => null);
      if (!accountsResponse.ok || !transactionsResponse.ok) {
        throw new Error(
          accountsData?.detail ||
            transactionsData?.detail ||
            'Nie udało się pobrać danych dashboardu.',
        );
      }

      const nextAccounts = accountsData?.accounts ?? [];
      setAccounts(nextAccounts);
      setTransactions(transactionsData?.transactions ?? []);
      setSelectedCurrency(current => (
        current && nextAccounts.some((account: Account) => account.currency_code === current)
          ? current
          : nextAccounts[0]?.currency_code ?? null
      ));
    } catch (loadError) {
      console.error('Nie udało się pobrać danych dashboardu:', loadError);
      setError(loadError instanceof Error ? loadError.message : 'Nie udało się pobrać danych dashboardu.');
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, token]);

  React.useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const selectedAccount = accounts.find(
    account => account.currency_code === selectedCurrency,
  );

  const formatTransactionDate = (date: string) => (
    new Intl.DateTimeFormat('pl-PL', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(date))
  );

  const transactionLabel = (transaction: Transaction) => {
    if (transaction.type === 'opening') {
      return 'Saldo początkowe';
    }
    if (transaction.direction === 'incoming') {
      return transaction.counterparty_email
        ? `Wpłata od ${transaction.counterparty_email}`
        : 'Wpłata';
    }
    if (transaction.direction === 'outgoing') {
      return transaction.counterparty_email
        ? `Przelew do ${transaction.counterparty_email}`
        : 'Przelew';
    }
    return 'Transakcja';
  };

  return (
    <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.content}>
            <BrandLogo />

            <Text style={styles.title}>
            Dashboard
            </Text>

            <Text style={styles.subtitle}>
            Panel użytkownika
            </Text>

            <Text style={styles.description}>
            Jesteś Zalogowany jako {username} :D
            </Text>

            <View style={styles.dataSection}>
              <Text style={styles.sectionTitle}>Twoje saldo</Text>
              {isLoading ? (
                <ActivityIndicator color={COLORS.yellow} />
              ) : error ? (
                <View style={styles.messageBox}>
                  <Text style={styles.errorText}>{error}</Text>
                  <AppButton title="Spróbuj ponownie" onPress={loadDashboardData} />
                </View>
              ) : (
                <>
                  <Pressable
                    accessibilityRole="button"
                    accessibilityLabel="Wybierz walutę salda"
                    onPress={() => setCurrencyPickerVisible(true)}
                    style={styles.currencySelector}>
                    <Text style={styles.currencyText}>
                      {selectedCurrency ?? 'Brak waluty'}
                    </Text>
                    <Text style={styles.selectorHint}>Zmień walutę</Text>
                  </Pressable>
                  <Text style={styles.balance}>
                    {selectedAccount?.balance ?? '0.00'} {selectedCurrency ?? ''}
                  </Text>

                  <Text style={styles.sectionTitle}>Najnowsze transakcje</Text>
                  <AppButton
                    title="Utwórz transakcję"
                    onPress={() => setCreationVisible(true)}
                  />
                  {transactions.length === 0 ? (
                    <Text style={styles.emptyText}>Brak transakcji.</Text>
                  ) : (
                    transactions.map(transaction => (
                      <Pressable
                        key={transaction.id}
                        accessibilityRole="button"
                        accessibilityLabel="Pokaż szczegóły transakcji"
                        onPress={() => setSelectedTransactionId(transaction.id)}
                        style={({pressed}) => [
                          styles.transaction,
                          pressed && styles.pressed,
                        ]}>
                        <View style={styles.transactionDetails}>
                          <Text style={styles.transactionLabel}>
                            {transactionLabel(transaction)}
                          </Text>
                          <Text style={styles.transactionDate}>
                            {formatTransactionDate(transaction.created_at)}
                          </Text>
                        </View>
                        <Text
                          style={[
                            styles.transactionAmount,
                            transaction.direction === 'outgoing' && styles.outgoing,
                          ]}>
                          {transaction.direction === 'outgoing' ? '-' : '+'}
                          {transaction.amount} {transaction.currency_code}
                        </Text>
                      </Pressable>
                    ))
                  )}
                </>
              )}
            </View>

            <View style={styles.buttons}>
              <AppButton
                title="Historia transakcji"
                onPress={onTransactionHistory}
              />
              <AppButton
                title="Kurs wymiany walut"
                onPress={onExchangeRates}
              />

              <AppButton
                title="Profil"
                onPress={onProfile}
                secondary
              />

              <AppButton
                title="Skaner QR"
                onPress={onQrScanner}
                secondary
              />

              <AppButton 
                title="Wyloguj się" 
                onPress={onLogout} 
                secondary
              />
            </View>
        </View>

        <Modal
          visible={isCurrencyPickerVisible}
          transparent
          animationType="fade"
          onRequestClose={() => setCurrencyPickerVisible(false)}>
          <Pressable
            style={styles.modalBackdrop}
            onPress={() => setCurrencyPickerVisible(false)}>
            <View style={styles.modalCard}>
              <Text style={styles.modalTitle}>Wybierz walutę</Text>
              {accounts.map(account => (
                <Pressable
                  key={account.id}
                  accessibilityRole="button"
                  onPress={() => {
                    setSelectedCurrency(account.currency_code);
                    setCurrencyPickerVisible(false);
                  }}
                  style={styles.currencyOption}>
                  <Text style={styles.currencyOptionText}>{account.currency_code}</Text>
                  <Text style={styles.currencyOptionBalance}>{account.balance}</Text>
                </Pressable>
              ))}
            </View>
          </Pressable>
        </Modal>
        <TransactionDetails
          transactionId={selectedTransactionId}
          token={token}
          onClose={() => setSelectedTransactionId(null)}
          goHome={goHome}
        />
        <TransactionCreation
          visible={isCreationVisible}
          token={token}
          accounts={accounts}
          onClose={() => setCreationVisible(false)}
          onCreated={loadDashboardData}
        />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 28,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 35,
  },
  title: {
    color: COLORS.yellow,
    fontSize: 34,
    fontWeight: '800',
    textAlign: 'center',
    marginTop: 30,
  },
  subtitle: {
    color: COLORS.white,
    fontSize: 20,
    marginTop: 10,
  },
  description: {
    color: COLORS.muted,
    fontSize: 15,
    textAlign: 'center',
    marginTop: 12,
  },
  buttons: {
    width: '100%',
    marginTop: 48,
    gap: 14,
  },
  dataSection: {
    width: '100%',
    marginTop: 30,
    gap: 12,
  },
  sectionTitle: {
    color: COLORS.white,
    fontSize: 20,
    fontWeight: '700',
    marginTop: 12,
  },
  currencySelector: {
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  currencyText: {
    color: COLORS.yellow,
    fontSize: 17,
    fontWeight: '700',
  },
  selectorHint: {
    color: COLORS.muted,
    fontSize: 14,
  },
  balance: {
    color: COLORS.white,
    fontSize: 30,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 8,
  },
  transaction: {
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    padding: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 10,
  },
  pressed: {
    opacity: 0.75,
  },
  transactionDetails: {
    flex: 1,
    gap: 5,
  },
  transactionLabel: {
    color: COLORS.white,
    fontSize: 14,
  },
  transactionDate: {
    color: COLORS.muted,
    fontSize: 12,
  },
  transactionAmount: {
    color: '#86EFAC',
    fontSize: 14,
    fontWeight: '700',
  },
  outgoing: {
    color: '#FCA5A5',
  },
  emptyText: {
    color: COLORS.muted,
    fontSize: 15,
  },
  messageBox: {
    gap: 12,
  },
  errorText: {
    color: '#FCA5A5',
    fontSize: 14,
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'center',
    padding: 24,
  },
  modalCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    padding: 22,
  },
  modalTitle: {
    color: COLORS.white,
    fontSize: 22,
    fontWeight: '700',
    marginBottom: 12,
  },
  currencyOption: {
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingVertical: 14,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  currencyOptionText: {
    color: COLORS.white,
    fontSize: 17,
    fontWeight: '700',
  },
  currencyOptionBalance: {
    color: COLORS.muted,
    fontSize: 16,
  },
  footer: {
    alignItems: 'center',
  },
  footerTitle: {
    color: COLORS.yellow,
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 10,
  },
  authors: {
    color: COLORS.muted,
    fontSize: 14,
    lineHeight: 24,
    textAlign: 'center',
  },
  backButton: {
    alignSelf: 'flex-start',
    paddingVertical: 12,
  },
  backText: {
    color: COLORS.white,
    fontSize: 17,
  },
});