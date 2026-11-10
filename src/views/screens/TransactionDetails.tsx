import React from 'react';
import {
  ActivityIndicator,
  Modal,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {API_URL} from '@env';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {AppButton} from '../components/Ui';
import {COLORS} from '../theme';
import type {TransactionDetailsData} from '../../types/TransactionDetailsData';
import type {TransactionDetailsProps} from '../../types/TransactionDetailsProps';

export function TransactionDetails({transactionId, token, onClose, goHome}: TransactionDetailsProps) {
  const [transaction, setTransaction] =
    React.useState<TransactionDetailsData | null>(null);
  const [isLoading, setIsLoading] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const insets = useSafeAreaInsets();
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  React.useEffect(() => {
    if (!transactionId) {
      setTransaction(null);
      setError(null);
      return;
    }

    let isCurrent = true;
    const requestedTransactionId = transactionId;

    async function loadTransaction() {
      if (!token) {
        setError('Brak aktywnego tokenu. Zaloguj się ponownie.');
        goHome();
        return;
      }

      setIsLoading(true);
      setError(null);
      try {
        const response = await fetch(
          `${apiBaseUrl}/api/transactions/${encodeURIComponent(requestedTransactionId)}`,
          {headers: {Authorization: `Bearer ${token}`}},
        );
        const data = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(data?.detail || 'Nie udało się pobrać transakcji.');
        }
        if (isCurrent) {
          setTransaction(data);
        }
      } catch (loadError) {
        console.error('Nie udało się pobrać szczegółów transakcji:', loadError);
        if (isCurrent) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : 'Nie udało się pobrać transakcji.',
          );
        }
      } finally {
        if (isCurrent) {
          setIsLoading(false);
        }
      }
    }

    loadTransaction();
    return () => {
      isCurrent = false;
    };
  }, [apiBaseUrl, token, transactionId]);

  const formatDate = (date: string) => (
    new Intl.DateTimeFormat('pl-PL', {
      dateStyle: 'medium',
      timeStyle: 'short',
    }).format(new Date(date))
  );

  return (
    <Modal
      visible={transactionId !== null}
      transparent
      animationType="slide"
      onRequestClose={onClose}>
      <View style={styles.backdrop}>
        <View
          style={[
            styles.card,
            {paddingBottom: Math.max(24, insets.bottom + 16)},
          ]}>
          <Text style={styles.title}>Szczegóły transakcji</Text>

          {isLoading ? (
            <ActivityIndicator color={COLORS.yellow} />
          ) : error ? (
            <Text style={styles.errorText}>{error}</Text>
          ) : transaction ? (
            <ScrollView contentContainerStyle={styles.details}>
              <Text style={styles.amount}>
                {transaction.direction === 'outgoing' ? '-' : '+'}
                {transaction.type === 'exchange'
                  ? transaction.destination_amount
                  : transaction.amount}{' '}
                {transaction.type === 'exchange'
                  ? transaction.destination_currency_code
                  : transaction.currency_code}
              </Text>
              <DetailRow label="Typ" value={transaction.type} />
              <DetailRow label="Status" value={transaction.status} />
              <DetailRow label="Kierunek" value={transaction.direction} />
              <DetailRow
                label="Odbiorca / nadawca"
                value={transaction.counterparty_email ?? 'Brak'}
              />
              <DetailRow label="Data" value={formatDate(transaction.created_at)} />
              {transaction.source_amount && transaction.source_currency_code && (
                <DetailRow
                  label="Kwota źródłowa"
                  value={`${transaction.source_amount} ${transaction.source_currency_code}`}
                />
              )}
              <DetailRow
                label="Kwota docelowa"
                value={`${transaction.destination_amount} ${transaction.destination_currency_code}`}
              />
              {transaction.exchange_rate && (
                <DetailRow label="Kurs wymiany" value={transaction.exchange_rate} />
              )}
            </ScrollView>
          ) : null}

          <AppButton title="Zamknij" onPress={onClose} secondary />
        </View>
      </View>
    </Modal>
  );
}

function DetailRow({label, value}: {label: string; value: string}) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      <Text style={styles.value}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
  },
  card: {
    backgroundColor: COLORS.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    maxHeight: '85%',
    gap: 18,
  },
  title: {
    color: COLORS.white,
    fontSize: 24,
    fontWeight: '800',
  },
  details: {
    gap: 14,
    paddingBottom: 4,
  },
  amount: {
    color: COLORS.yellow,
    fontSize: 28,
    fontWeight: '800',
    marginBottom: 4,
  },
  row: {
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingTop: 10,
    gap: 4,
  },
  label: {
    color: COLORS.muted,
    fontSize: 13,
  },
  value: {
    color: COLORS.white,
    fontSize: 16,
  },
  errorText: {
    color: '#FCA5A5',
    fontSize: 15,
  },
});
