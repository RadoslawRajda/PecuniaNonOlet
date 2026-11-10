import React from 'react';
import {
  ActivityIndicator,
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
import type {Transaction} from '../../types/Transaction';
import type {TransactionHistoryScreenProps} from '../../types/TransactionHistoryScreenProps';

export function TransactionHistoryScreen({token, onBack, goHome}: TransactionHistoryScreenProps) {
  const [transactions, setTransactions] = React.useState<Transaction[]>([]);
  const [selectedTransactionId, setSelectedTransactionId] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  const loadHistory = React.useCallback(async () => {
    if (!token) {
      setError('Brak aktywnego tokenu. Zaloguj się ponownie.');
      setIsLoading(false);
      goHome();
      return;
    }

    setIsLoading(true);
    setError(null);
    try {
      const allTransactions: Transaction[] = [];
      let offset = 0;
      const limit = 100;
      let total = 0;

      do {
        const response = await fetch(
          `${apiBaseUrl}/api/transactions?limit=${limit}&offset=${offset}`,
          {headers: {Authorization: `Bearer ${token}`}},
        );
        const data = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(data?.detail || 'Nie udało się pobrać historii transakcji.');
        }

        const page: Transaction[] = data?.transactions ?? [];
        allTransactions.push(...page);
        total = data?.total ?? allTransactions.length;
        offset += page.length;
        if (page.length === 0) {
          break;
        }
      } while (offset < total);

      setTransactions(allTransactions);
    } catch (loadError) {
      console.error('Nie udało się pobrać historii transakcji:', loadError);
      setError(
        loadError instanceof Error
          ? loadError.message
          : 'Nie udało się pobrać historii transakcji.',
      );
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, token]);

  React.useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  const formatDate = (date: string) => new Intl.DateTimeFormat('pl-PL', {
    day: '2-digit',
    month: '2-digit',
    year: 'numeric',
  }).format(new Date(date));

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
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.container}>
        <BrandLogo />
        <Text style={styles.title}>Historia transakcji</Text>
        <Text style={styles.subtitle}>Wszystkie transakcje użytkownika</Text>

        {isLoading ? (
          <ActivityIndicator color={COLORS.yellow} style={styles.loader} />
        ) : error ? (
          <View style={styles.message}>
            <Text style={styles.errorText}>{error}</Text>
            <AppButton title="Spróbuj ponownie" onPress={loadHistory} />
          </View>
        ) : transactions.length === 0 ? (
          <Text style={styles.emptyText}>Brak transakcji.</Text>
        ) : (
          <View style={styles.list}>
            {transactions.map(transaction => (
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
                  <Text style={styles.date}>{formatDate(transaction.created_at)}</Text>
                </View>
                <Text
                  style={[
                    styles.amount,
                    transaction.direction === 'outgoing' && styles.outgoing,
                  ]}>
                  {transaction.direction === 'outgoing' ? '-' : '+'}
                  {transaction.type === 'exchange'
                    ? transaction.destination_amount
                    : transaction.amount}{' '}
                  {transaction.type === 'exchange'
                    ? transaction.destination_currency_code
                    : transaction.currency_code}
                </Text>
              </Pressable>
            ))}
          </View>
        )}

        <AppButton title="Wróć do dashboardu" onPress={onBack} secondary />
      </ScrollView>

      <TransactionDetails
        transactionId={selectedTransactionId}
        token={token}
        onClose={() => setSelectedTransactionId(null)}
        goHome={goHome}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  container: {
    flexGrow: 1,
    padding: 24,
    paddingTop: 32,
    gap: 14,
  },
  title: {
    color: COLORS.yellow,
    fontSize: 30,
    fontWeight: '800',
    marginTop: 18,
  },
  subtitle: {
    color: COLORS.muted,
    fontSize: 15,
    marginBottom: 10,
  },
  loader: {
    marginTop: 30,
  },
  list: {
    gap: 10,
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
  transactionDetails: {
    flex: 1,
    gap: 5,
  },
  transactionLabel: {
    color: COLORS.white,
    fontSize: 14,
  },
  date: {
    color: COLORS.muted,
    fontSize: 12,
  },
  amount: {
    color: '#86EFAC',
    fontSize: 14,
    fontWeight: '700',
  },
  outgoing: {
    color: '#FCA5A5',
  },
  pressed: {
    opacity: 0.75,
  },
  emptyText: {
    color: COLORS.muted,
    fontSize: 15,
    marginTop: 20,
  },
  message: {
    gap: 12,
  },
  errorText: {
    color: '#FCA5A5',
    fontSize: 14,
  },
});
