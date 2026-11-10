import React, {useCallback, useEffect, useMemo, useState} from 'react';
import {ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';
import {API_URL} from '@env';
import {WebView} from 'react-native-webview';

import {AppButton, BrandLogo, FormInput} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import type {Account} from '../../types/Account';
import type {BackScreenProps} from '../../types/BackScreenProps';
import {TransactionDetails} from './TransactionDetails';
import {useAppPreferences} from '../../context/AppPreferences';

type ExchangeRatesProps = {token: string | null; goHome: () => void};
type ExchangeRate = {currency_code: string; pln_per_unit: string};
type Quote = {
  quote_id: string;
  source_amount: string;
  destination_amount: string;
  source_currency_code: string;
  destination_currency_code: string;
  exchange_rate: string;
  provider: string;
  effective_date: string;
  expires_at: string;
};

export function ExchangeRatesScreen({token, goHome}: ExchangeRatesProps) {
  const {preferredCurrency} = useAppPreferences();
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [rates, setRates] = useState<ExchangeRate[]>([]);
  const [provider, setProvider] = useState('');
  const [effectiveDate, setEffectiveDate] = useState('');
  const [sourceAccountId, setSourceAccountId] = useState<number | null>(null);
  const [destinationAccountId, setDestinationAccountId] = useState<number | null>(null);
  const [amount, setAmount] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [transactionId, setTransactionId] = useState<string | null>(null);
  const [isExchangeMenuVisible, setExchangeMenuVisible] = useState(false);
  const [isSourcePageVisible, setSourcePageVisible] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isQuoting, setIsQuoting] = useState(false);
  const [isExchanging, setIsExchanging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const sourceAccount = accounts.find(account => account.id === sourceAccountId) ?? null;
  const destinationAccount = accounts.find(account => account.id === destinationAccountId) ?? null;
  const normalizedAmount = amount.trim().replace(',', '.');
  const validAmount = /^\d+(\.\d{1,2})?$/.test(normalizedAmount) && Number(normalizedAmount) > 0;

  const loadData = useCallback(async () => {
    if (!token) {
      setError('Brak aktywnej sesji. Zaloguj się ponownie.');
      setIsLoading(false);
      goHome();
      return;
    }
    setIsLoading(true);
    setError(null);
    try {
      const headers = {Authorization: `Bearer ${token}`};
      const [rateResponse, accountResponse] = await Promise.all([
        fetch(`${apiBaseUrl}/api/exchange-rates`, {headers}),
        fetch(`${apiBaseUrl}/api/accounts`, {headers}),
      ]);
      const [rateData, accountData] = await Promise.all([
        rateResponse.json().catch(() => null),
        accountResponse.json().catch(() => null),
      ]);
      if (!rateResponse.ok || !accountResponse.ok) {
        throw new Error(rateData?.detail || accountData?.detail || 'Nie udało się pobrać kursów lub rachunków.');
      }
      const nextAccounts: Account[] = accountData?.accounts ?? [];
      setRates(rateData?.rates ?? []);
      setProvider(rateData?.provider ?? '');
      setEffectiveDate(rateData?.effective_date ?? '');
      setAccounts(nextAccounts);
      const preferredAccount = nextAccounts.find(account => account.currency_code === preferredCurrency);
      const defaultSource = preferredAccount ?? nextAccounts[0];
      const defaultDestination = nextAccounts.find(account => account.id !== defaultSource?.id);
      setSourceAccountId(current => current && nextAccounts.some(account => account.id === current)
        ? current : defaultSource?.id ?? null);
      setDestinationAccountId(current => current && current !== defaultSource?.id && nextAccounts.some(account => account.id === current)
        ? current : defaultDestination?.id ?? null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Nie udało się pobrać danych wymiany.');
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, goHome, preferredCurrency, token]);

  useEffect(() => { loadData(); }, [loadData]);

  const sourceAmountMinor = useMemo(
    () => Math.round(Number(normalizedAmount) * 100),
    [normalizedAmount],
  );
  const canRequestQuote = Boolean(
    token && sourceAccount && destinationAccount && sourceAccount.id !== destinationAccount.id &&
    sourceAccount.currency_code !== destinationAccount.currency_code && validAmount &&
    sourceAmountMinor > 0 && sourceAmountMinor <= 9_000_000_000_000_000,
  );

  const requestQuote = async () => {
    if (!canRequestQuote || !sourceAccount || !destinationAccount || !token) {
      setError('Wybierz dwa różne rachunki i podaj poprawną kwotę.');
      return;
    }
    setIsQuoting(true);
    setError(null);
    setQuote(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/exchange/quote`, {
        method: 'POST',
        headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
        body: JSON.stringify({
          source_account_id: sourceAccount.id,
          destination_account_id: destinationAccount.id,
          source_amount_minor: sourceAmountMinor,
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || 'Nie udało się pobrać wyceny.');
      }
      setQuote(data);
    } catch (quoteError) {
      setError(quoteError instanceof Error ? quoteError.message : 'Nie udało się pobrać wyceny.');
    } finally {
      setIsQuoting(false);
    }
  };

  const executeExchange = async () => {
    if (!quote || !token) {
      return;
    }
    setIsExchanging(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/exchange`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Idempotency-Key': `exchange-${Date.now()}-${Math.random().toString(36).slice(2)}`,
        },
        body: JSON.stringify({quote_id: quote.quote_id}),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || 'Nie udało się wymienić środków. Pobierz nową wycenę.');
      }
      setQuote(null);
      setAmount('');
      await loadData();
      setExchangeMenuVisible(false);
      setTransactionId(data.transaction_id);
    } catch (exchangeError) {
      setError(exchangeError instanceof Error ? exchangeError.message : 'Nie udało się wymienić środków.');
    } finally {
      setIsExchanging(false);
    }
  };

  const chooseAccount = (account: Account, field: 'source' | 'destination') => {
    setQuote(null);
    if (field === 'source') {
      setSourceAccountId(account.id);
      if (destinationAccountId === account.id) {
        setDestinationAccountId(accounts.find(item => item.id !== account.id)?.id ?? null);
      }
    } else {
      setDestinationAccountId(account.id);
      if (sourceAccountId === account.id) {
        setSourceAccountId(accounts.find(item => item.id !== account.id)?.id ?? null);
      }
    }
  };

  return (
    <>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.content}>
          <BrandLogo />
          <Text style={styles.title}>Kursy i wymiana walut</Text>
          {isLoading ? <ActivityIndicator color={COLORS.yellow} /> : null}

          <Text style={styles.sectionTitle}>Aktualne kursy</Text>
          {provider ? <Text style={styles.muted}>{provider} · tabela z {effectiveDate}</Text> : null}
          {rates.map(rate => (
            <View key={rate.currency_code} style={styles.rateRow}>
              <Text style={styles.rateCurrency}>1 {rate.currency_code}</Text>
              <Text style={styles.rateValue}>{rate.pln_per_unit} PLN</Text>
            </View>
          ))}
          <Text style={styles.sectionTitle}>Kursy na stronie NBP</Text>
          <Text style={styles.muted}>Oficjalna tabela źródłowa używana przez aplikację.</Text>
          <AppButton title="Otwórz stronę NBP" onPress={() => setSourcePageVisible(true)} secondary />
          <View style={styles.backButton}>
            <AppButton title="Wymień waluty" onPress={() => setExchangeMenuVisible(true)} />
          </View>
          <View style={styles.backButton}>
          </View>
        </View>
      </ScrollView>
      <Modal
        visible={isSourcePageVisible}
        animationType="slide"
        onRequestClose={() => setSourcePageVisible(false)}>
        <View style={styles.sourcePage}>
          <View style={styles.sourcePageHeader}>
            <Text style={styles.sourcePageTitle}>Kursy walut NBP</Text>
            <Pressable accessibilityRole="button" onPress={() => setSourcePageVisible(false)}>
              <Text style={styles.sourcePageClose}>Zamknij</Text>
            </Pressable>
          </View>
          <WebView
            source={{uri: 'https://nbp.pl/statystyka-i-sprawozdawczosc/kursy/tabela-a/'} }
            startInLoadingState
            javaScriptEnabled
            domStorageEnabled
            scrollEnabled
            nestedScrollEnabled
            style={styles.webView}
          />
        </View>
      </Modal>
      <Modal
        visible={isExchangeMenuVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setExchangeMenuVisible(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <ScrollView keyboardShouldPersistTaps="handled" contentContainerStyle={styles.exchangeForm}>
              <Text style={styles.modalTitle}>Wymień środki</Text>
              <Text style={styles.label}>Z rachunku</Text>
              <View style={styles.accountList}>
                {accounts.map(account => (
                  <Pressable key={`source-${account.id}`} onPress={() => chooseAccount(account, 'source')}
                    style={[styles.accountOption, sourceAccountId === account.id && styles.selected]}>
                    <Text style={styles.accountText}>{account.currency_code} · {account.balance}</Text>
                  </Pressable>
                ))}
              </View>
              <Text style={styles.label}>Na rachunek</Text>
              <View style={styles.accountList}>
                {accounts.map(account => (
                  <Pressable key={`destination-${account.id}`} onPress={() => chooseAccount(account, 'destination')}
                    style={[styles.accountOption, destinationAccountId === account.id && styles.selected]}>
                    <Text style={styles.accountText}>{account.currency_code} · {account.balance}</Text>
                  </Pressable>
                ))}
              </View>
              <FormInput
                label={`Kwota${sourceAccount ? ` (${sourceAccount.currency_code})` : ''}`}
                value={amount}
                onChangeText={value => { setAmount(value); setQuote(null); }}
                keyboardType="decimal-pad"
                placeholder="0.00"
              />
              {isQuoting ? <ActivityIndicator color={COLORS.yellow} /> : (
                <AppButton title="Pobierz wycenę" onPress={requestQuote} />
              )}
              {quote ? (
                <View style={styles.quoteCard}>
                  <Text style={styles.quoteTitle}>Podsumowanie wymiany</Text>
                  <Text style={styles.quoteText}>Oddasz: {quote.source_amount} {quote.source_currency_code}</Text>
                  <Text style={styles.quoteText}>Otrzymasz: {quote.destination_amount} {quote.destination_currency_code}</Text>
                  <Text style={styles.quoteText}>Kurs: 1 {quote.source_currency_code} = {quote.exchange_rate} {quote.destination_currency_code}</Text>
                  <Text style={styles.muted}>Wycena wygasa: {new Date(quote.expires_at).toLocaleTimeString('pl-PL')}</Text>
                  {isExchanging ? <ActivityIndicator color={COLORS.yellow} /> : (
                    <AppButton title="Potwierdź wymianę" onPress={executeExchange} />
                  )}
                </View>
              ) : null}
              {error ? <Text style={styles.error}>{error}</Text> : null}
              <AppButton title="Zamknij" onPress={() => setExchangeMenuVisible(false)} secondary />
            </ScrollView>
          </View>
        </View>
      </Modal>
      <TransactionDetails
        transactionId={transactionId}
        token={token}
        onClose={() => setTransactionId(null)}
        goHome={goHome}
      />
    </>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {flexGrow: 1, paddingHorizontal: 24, paddingVertical: 20},
  content: {flexGrow: 1, alignItems: 'center', paddingVertical: 35, gap: 12},
  title: {color: COLORS.yellow, fontSize: 30, fontWeight: '800', textAlign: 'center', marginTop: 24, marginBottom: 12},
  sectionTitle: {alignSelf: 'stretch', color: COLORS.white, fontSize: 20, fontWeight: '700', marginTop: 18},
  muted: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 13},
  rateRow: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 12, padding: 14, flexDirection: 'row', justifyContent: 'space-between'},
  rateCurrency: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
  rateValue: {color: COLORS.yellow, fontSize: 16, fontWeight: '700'},
  label: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 14, fontWeight: '600', marginTop: 6},
  accountList: {alignSelf: 'stretch', gap: 6},
  accountOption: {backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 10, padding: 12},
  selected: {borderColor: COLORS.yellow},
  accountText: {color: COLORS.white, fontSize: 15},
  quoteCard: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderRadius: 14, padding: 16, gap: 12, marginTop: 8},
  quoteTitle: {color: COLORS.yellow, fontSize: 18, fontWeight: '700'},
  quoteText: {color: COLORS.white, fontSize: 15},
  error: {alignSelf: 'stretch', color: '#FCA5A5', fontSize: 14},
  backButton: {alignSelf: 'stretch', marginTop: 16},
  sourcePage: {flex: 1, backgroundColor: COLORS.background},
  sourcePageHeader: {backgroundColor: COLORS.surface, paddingHorizontal: 18, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  sourcePageTitle: {color: COLORS.white, fontSize: 17, fontWeight: '700'},
  sourcePageClose: {color: COLORS.yellow, fontSize: 15, fontWeight: '700', padding: 6},
  webView: {flex: 1, backgroundColor: '#FFFFFF'},
  modalBackdrop: {flex: 1, justifyContent: 'center', backgroundColor: 'rgba(0,0,0,0.7)', padding: 20},
  modalCard: {maxHeight: '90%', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 18, padding: 20},
  exchangeForm: {gap: 12, paddingBottom: 4},
  modalTitle: {color: COLORS.white, fontSize: 22, fontWeight: '800', marginBottom: 4},
}));
