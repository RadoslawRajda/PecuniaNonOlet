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
import ArrowRightLeft from 'lucide-react-native/icons/arrow-right-left';
import QrCode from 'lucide-react-native/icons/qr-code';
import ChevronRight from 'lucide-react-native/icons/chevron-right';
import {API_URL} from '@env';

import {AppButton, ScreenHeader} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import {TransactionDetails} from './TransactionDetails';
import {TransactionCreation} from './TransactionCreation';
import type {Account} from '../../types/Account';
import type {Transaction} from '../../types/Transaction';
import type {DashboardProps} from '../../types/DashboardProps';
import {useAppPreferences} from '../../context/AppPreferences';

export function Dashboard({
  username,
  token,
  goHome,
  onExchange,
  onQr,
  onHistory,
}: DashboardProps) {
  const {preferredCurrency} = useAppPreferences();
  const [accounts, setAccounts] = React.useState<Account[]>([]);
  const [transactions, setTransactions] = React.useState<Transaction[]>([]);
  const [selectedCurrency, setSelectedCurrency] = React.useState<string | null>(null);
  const [isCurrencyPickerVisible, setCurrencyPickerVisible] = React.useState(false);
  const [selectedTransactionId, setSelectedTransactionId] = React.useState<string | null>(null);
  const [isCreationVisible, setCreationVisible] = React.useState(false);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const previousPreferredCurrency = React.useRef(preferredCurrency);
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
          : nextAccounts.find((account: Account) => account.currency_code === preferredCurrency)?.currency_code
            ?? nextAccounts[0]?.currency_code
            ?? null
      ));
    } catch (loadError) {
      console.error('Nie udało się pobrać danych dashboardu:', loadError);
      setError(loadError instanceof Error ? loadError.message : 'Nie udało się pobrać danych dashboardu.');
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, goHome, preferredCurrency, token]);

  React.useEffect(() => {
    loadDashboardData();
  }, [loadDashboardData]);

  const selectedAccount = accounts.find(
    account => account.currency_code === selectedCurrency,
  );

  React.useEffect(() => {
    const preferenceChanged = previousPreferredCurrency.current !== preferredCurrency;
    previousPreferredCurrency.current = preferredCurrency;
    if (preferenceChanged && preferredCurrency && accounts.some(account => account.currency_code === preferredCurrency)) {
      setSelectedCurrency(preferredCurrency);
    }
  }, [accounts, preferredCurrency]);

  const formatTransactionDate = (date: string) => (
    new Intl.DateTimeFormat('pl-PL', {
      day: '2-digit',
      month: '2-digit',
      year: 'numeric',
    }).format(new Date(date))
  );

  const transactionLabel = (transaction: Transaction) => {
    if (transaction.type === 'exchange') {
      return 'Wymiana walut';
    }
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
        <ScreenHeader title={`Cześć, ${username}`} subtitle="Twoje finanse w jednym miejscu" />

        <View style={styles.balanceCard}>
          <Text style={styles.balanceCaption}>Dostępne środki</Text>
          {isLoading ? <ActivityIndicator color={COLORS.yellow} /> : error ? (
            <View style={styles.messageBox}>
              <Text style={styles.errorText}>{error}</Text>
              <AppButton title="Spróbuj ponownie" onPress={loadDashboardData} />
            </View>
          ) : (
            <>
              <Pressable accessibilityRole="button" accessibilityLabel="Wybierz walutę salda" onPress={() => setCurrencyPickerVisible(true)} style={styles.currencySelector}>
                <Text style={styles.currencyText}>{selectedCurrency ?? 'Brak waluty'}</Text>
                <Text style={styles.selectorHint}>Zmień walutę</Text>
              </Pressable>
              <Text style={styles.balance}>{selectedAccount?.balance ?? '0.00'} {selectedCurrency ?? ''}</Text>
              <Text style={styles.balanceFootnote}>Saldo na wybranym rachunku</Text>
            </>
          )}
        </View>

        <View style={styles.sectionHeading}>
          <Text style={styles.sectionTitle}>Szybkie działania</Text>
        </View>
        <Pressable accessibilityRole="button" onPress={() => setCreationVisible(true)} style={({pressed}) => [styles.transferAction, pressed && styles.pressed]}>
          <ArrowRightLeft size={22} color={COLORS.darkText} strokeWidth={2.5} />
          <Text style={styles.transferActionText}>Nowy przelew</Text>
          <ChevronRight size={20} color={COLORS.darkText} />
        </Pressable>
        <View style={styles.secondaryActions}>
          <Pressable accessibilityRole="button" onPress={onExchange} style={({pressed}) => [styles.secondaryAction, pressed && styles.pressed]}>
            <ArrowRightLeft size={20} color={COLORS.yellow} />
            <Text style={styles.secondaryActionText}>Wymień</Text>
          </Pressable>
          <Pressable accessibilityRole="button" onPress={onQr} style={({pressed}) => [styles.secondaryAction, pressed && styles.pressed]}>
            <QrCode size={20} color={COLORS.yellow} />
            <Text style={styles.secondaryActionText}>Kod QR</Text>
          </Pressable>
        </View>

        <View style={styles.sectionHeading}>
          <Text style={styles.sectionTitle}>Ostatnie transakcje</Text>
          <Pressable accessibilityRole="button" onPress={onHistory} style={styles.historyLink}>
            <Text style={styles.historyLinkText}>Zobacz wszystkie</Text>
          </Pressable>
        </View>
        {isLoading ? null : transactions.length === 0 ? <Text style={styles.emptyText}>Brak transakcji.</Text> : (
          transactions.slice(0, 5).map(transaction => (
            <Pressable key={transaction.id} accessibilityRole="button" accessibilityLabel="Pokaż szczegóły transakcji" onPress={() => setSelectedTransactionId(transaction.id)} style={({pressed}) => [styles.transaction, pressed && styles.pressed]}>
              <View style={styles.transactionDetails}>
                <Text style={styles.transactionLabel}>{transactionLabel(transaction)}</Text>
                <Text style={styles.transactionDate}>{formatTransactionDate(transaction.created_at)}</Text>
              </View>
              <Text style={[styles.transactionAmount, transaction.direction === 'outgoing' && styles.outgoing]}>
                {transaction.direction === 'outgoing' ? '-' : '+'}{transaction.type === 'exchange' ? transaction.destination_amount : transaction.amount}{' '}{transaction.type === 'exchange' ? transaction.destination_currency_code : transaction.currency_code}
              </Text>
            </Pressable>
          ))
        )}
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
          onCreated={transactionId => {
            loadDashboardData();
            setSelectedTransactionId(transactionId ?? null);
          }}
        />
    </ScrollView>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {
    flexGrow: 1, paddingHorizontal: 20, paddingTop: 16, paddingBottom: 28,
  },
  content: {
    flexGrow: 1, gap: 14,
  },
  balanceCard: {backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 18, padding: 20, gap: 8},
  balanceCaption: {color: COLORS.muted, fontSize: 14, fontWeight: '600'},
  sectionTitle: {color: COLORS.white, fontSize: 19, fontWeight: '800'},
  sectionHeading: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8},
  transferAction: {minHeight: 64, backgroundColor: COLORS.yellow, borderRadius: 15, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', gap: 12},
  transferActionText: {flex: 1, color: COLORS.darkText, fontSize: 17, fontWeight: '800'},
  secondaryActions: {flexDirection: 'row', gap: 12},
  secondaryAction: {flex: 1, minHeight: 58, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 9},
  secondaryActionText: {color: COLORS.white, fontSize: 15, fontWeight: '700'},
  historyLink: {minHeight: 44, justifyContent: 'center', paddingHorizontal: 4},
  historyLinkText: {color: COLORS.yellow, fontSize: 13, fontWeight: '700'},
  currencySelector: {
    alignSelf: 'flex-start', backgroundColor: COLORS.input, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 8, flexDirection: 'row', alignItems: 'center', gap: 10,
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
    marginTop: 2,
  },
  balanceFootnote: {color: COLORS.muted, fontSize: 12},
  transaction: {
    backgroundColor: COLORS.surface, borderRadius: 12, borderWidth: 1, borderColor: COLORS.border, padding: 14,
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
}));
