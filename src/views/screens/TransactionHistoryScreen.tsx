import React from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {API_URL} from '@env';

import {AppButton, ScreenHeader} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import {TransactionDetails} from './TransactionDetails';
import type {Transaction} from '../../types/Transaction';
import type {TransactionHistoryScreenProps} from '../../types/TransactionHistoryScreenProps';

export function TransactionHistoryScreen({token, goHome}: TransactionHistoryScreenProps) {
  const [transactions, setTransactions] = React.useState<Transaction[]>([]);
  const [selectedTransactionId, setSelectedTransactionId] = React.useState<string | null>(null);
  const [isLoading, setIsLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [filter, setFilter] = React.useState<'all' | 'incoming' | 'outgoing'>('all');
  const [search, setSearch] = React.useState('');
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
  }, [apiBaseUrl, goHome, token]);

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

  const visibleTransactions = transactions.filter(transaction => {
    const matchesDirection = filter === 'all' || transaction.direction === filter;
    const query = search.trim().toLocaleLowerCase('pl-PL');
    const matchesSearch = !query || [transactionLabel(transaction), transaction.currency_code, transaction.counterparty_email ?? '']
      .some(value => value.toLocaleLowerCase('pl-PL').includes(query));
    return matchesDirection && matchesSearch;
  });

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.container}>
        <ScreenHeader title="Historia" subtitle="Wszystkie Twoje transakcje" />

        <View style={styles.filters}>
          {FILTERS.map(item => (
            <Pressable key={item.value} accessibilityRole="button" accessibilityState={{selected: filter === item.value}}
              onPress={() => setFilter(item.value)} style={[styles.filterChip, filter === item.value && styles.filterChipActive]}>
              <Text style={[styles.filterText, filter === item.value && styles.filterTextActive]}>{item.label}</Text>
            </Pressable>
          ))}
        </View>
        <TextInput value={search} onChangeText={setSearch} placeholder="Szukaj transakcji" placeholderTextColor={COLORS.muted}
          accessibilityLabel="Szukaj transakcji" style={styles.searchInput} returnKeyType="search" />

        {isLoading ? (
          <ActivityIndicator color={COLORS.yellow} style={styles.loader} />
        ) : error ? (
          <View style={styles.message}>
            <Text style={styles.errorText}>{error}</Text>
            <AppButton title="Spróbuj ponownie" onPress={loadHistory} />
          </View>
        ) : transactions.length === 0 ? (
          <Text style={styles.emptyText}>Brak transakcji.</Text>
        ) : visibleTransactions.length === 0 ? (
          <Text style={styles.emptyText}>Brak transakcji pasujących do filtrów.</Text>
        ) : (
          <View style={styles.list}>
            {visibleTransactions.map((transaction, index) => (
              <React.Fragment key={transaction.id}>
                {(index === 0 || formatDate(visibleTransactions[index - 1].created_at) !== formatDate(transaction.created_at)) ? (
                  <Text style={styles.groupDate}>{formatDate(transaction.created_at)}</Text>
                ) : null}
              <Pressable
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
              </React.Fragment>
            ))}
          </View>
        )}

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

const styles = createThemedStyles(() => StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  container: {
    flexGrow: 1,
    padding: 20, paddingTop: 16, gap: 12,
  },
  filters: {flexDirection: 'row', gap: 8},
  filterChip: {flex: 1, minHeight: 42, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: COLORS.border, borderRadius: 12, backgroundColor: COLORS.surface, paddingHorizontal: 6},
  filterChipActive: {backgroundColor: COLORS.yellow, borderColor: COLORS.yellow},
  filterText: {color: COLORS.muted, fontSize: 13, fontWeight: '700'},
  filterTextActive: {color: COLORS.darkText},
  searchInput: {minHeight: 48, borderRadius: 12, borderWidth: 1, borderColor: COLORS.border, backgroundColor: COLORS.input, paddingHorizontal: 14, color: COLORS.white, fontSize: 15},
  groupDate: {color: COLORS.muted, fontSize: 13, fontWeight: '700', marginTop: 8},
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
}));

const FILTERS = [
  {value: 'all', label: 'Wszystkie'},
  {value: 'incoming', label: 'Wpływy'},
  {value: 'outgoing', label: 'Wydatki'},
] as const;
