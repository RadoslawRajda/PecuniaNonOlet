import React, {useCallback, useEffect, useRef, useState} from 'react';
import {ActivityIndicator, Modal, Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';
import {API_URL} from '@env';
import {SafeAreaProvider, SafeAreaView} from 'react-native-safe-area-context';
import {WebView} from 'react-native-webview';
import ChevronDown from 'lucide-react-native/icons/chevron-down';
import ArrowLeftRight from 'lucide-react-native/icons/arrow-left-right';
import X from 'lucide-react-native/icons/x';

import {AppButton, FormInput, ScreenHeader} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import type {Account} from '../../types/Account';
import {TransactionDetails} from './TransactionDetails';
import {useAppPreferences} from '../../context/AppPreferences';
import {formatExchangeRate, formatExchangeRateLabel} from '../formatters';
import {estimateExchangeAmount, parseExchangeAmountMinor} from '../exchange';

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
  const [picker, setPicker] = useState<'source' | 'destination' | null>(null);
  const [isSourcePageVisible, setSourcePageVisible] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isQuoting, setIsQuoting] = useState(false);
  const [isExchanging, setIsExchanging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exchangeInFlight = useRef(false);
  const idempotencyKey = useRef<string | null>(null);

  const sourceAccount = accounts.find(account => account.id === sourceAccountId) ?? null;
  const destinationAccount = accounts.find(account => account.id === destinationAccountId) ?? null;
  const preferredRate = rates.find(rate => rate.currency_code === preferredCurrency);
  const preferredRateValue = preferredCurrency === 'PLN' ? 1 : Number(preferredRate?.pln_per_unit);
  const ratesInPreferredCurrency = rates.map(rate => {
    const rateInPln = Number(rate.pln_per_unit);
    return {...rate, value: Number.isFinite(rateInPln) && Number.isFinite(preferredRateValue) && preferredRateValue > 0 ? rateInPln / preferredRateValue : null};
  });
  const sourceAmountMinor = parseExchangeAmountMinor(amount);
  const estimatedAmount = sourceAccount && destinationAccount
    ? estimateExchangeAmount(amount, sourceAccount.currency_code, destinationAccount.currency_code, rates)
    : null;
  const canRequestQuote = Boolean(token && sourceAccount && destinationAccount && sourceAccount.id !== destinationAccount.id && sourceAccount.currency_code !== destinationAccount.currency_code && sourceAmountMinor !== null);

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
      const [rateData, accountData] = await Promise.all([rateResponse.json().catch(() => null), accountResponse.json().catch(() => null)]);
      if (!rateResponse.ok || !accountResponse.ok) throw new Error(rateData?.detail || accountData?.detail || 'Nie udało się pobrać kursów lub rachunków.');
      const nextAccounts: Account[] = accountData?.accounts ?? [];
      const nextRates: ExchangeRate[] = Array.isArray(rateData?.rates) ? rateData.rates : [];
      setRates(nextRates);
      setProvider(rateData?.provider ?? '');
      setEffectiveDate(rateData?.effective_date ?? '');
      setAccounts(nextAccounts);
      const preferredAccount = nextAccounts.find(account => account.currency_code === preferredCurrency);
      const defaultSource = preferredAccount ?? nextAccounts[0];
      const defaultDestination = nextAccounts.find(account => account.id !== defaultSource?.id);
      setSourceAccountId(current => current && nextAccounts.some(account => account.id === current) ? current : defaultSource?.id ?? null);
      setDestinationAccountId(current => current && current !== defaultSource?.id && nextAccounts.some(account => account.id === current) ? current : defaultDestination?.id ?? null);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Nie udało się pobrać danych wymiany.');
    } finally {
      setIsLoading(false);
    }
  }, [apiBaseUrl, goHome, preferredCurrency, token]);

  useEffect(() => { loadData(); }, [loadData]);

  const invalidateQuote = () => {
    setQuote(null);
    idempotencyKey.current = null;
    setError(null);
  };

  const requestQuote = async () => {
    if (!canRequestQuote || !sourceAccount || !destinationAccount || !token || sourceAmountMinor === null) {
      setError('Wybierz dwa różne rachunki i podaj poprawną kwotę.');
      return;
    }
    setIsQuoting(true);
    setError(null);
    setQuote(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/exchange/quote`, {
        method: 'POST', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
        body: JSON.stringify({source_account_id: sourceAccount.id, destination_account_id: destinationAccount.id, source_amount_minor: sourceAmountMinor}),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) throw new Error(data?.detail || 'Nie udało się pobrać wyceny.');
      setQuote(data);
      idempotencyKey.current = `exchange-${data.quote_id}`;
    } catch (quoteError) {
      setError(quoteError instanceof Error ? quoteError.message : 'Nie udało się pobrać wyceny.');
    } finally {
      setIsQuoting(false);
    }
  };

  const executeExchange = async () => {
    if (!quote || !token || exchangeInFlight.current) return;
    exchangeInFlight.current = true;
    setIsExchanging(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/exchange`, {
        method: 'POST',
        headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey.current ?? `exchange-${quote.quote_id}`},
        body: JSON.stringify({quote_id: quote.quote_id}),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        if (response.status === 409) invalidateQuote();
        throw new Error(data?.detail || 'Nie udało się wymienić środków. Pobierz nową wycenę.');
      }
      setQuote(null);
      idempotencyKey.current = null;
      setAmount('');
      await loadData();
      setTransactionId(data.transaction_id);
    } catch (exchangeError) {
      setError(exchangeError instanceof Error ? exchangeError.message : 'Nie udało się wymienić środków.');
    } finally {
      exchangeInFlight.current = false;
      setIsExchanging(false);
    }
  };

  const chooseAccount = (account: Account) => {
    invalidateQuote();
    if (picker === 'source') {
      setSourceAccountId(account.id);
      if (destinationAccountId === account.id) setDestinationAccountId(accounts.find(item => item.id !== account.id)?.id ?? null);
    } else {
      setDestinationAccountId(account.id);
      if (sourceAccountId === account.id) setSourceAccountId(accounts.find(item => item.id !== account.id)?.id ?? null);
    }
    setPicker(null);
  };

  return (
    <>
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <ScreenHeader title="Wymiana" subtitle="Kursy i wymiana walut" />
        {isLoading ? <ActivityIndicator color={COLORS.yellow} /> : null}
        {error && !quote ? <Text style={styles.error}>{error}</Text> : null}

        <View style={styles.ratesCard}>
          <View style={styles.sectionHeading}>
            <Text style={styles.sectionTitle}>Kursy walut</Text>
            <Pressable accessibilityRole="button" onPress={() => setSourcePageVisible(true)} style={styles.sourceLink}>
              <Text style={styles.sourceLinkText}>NBP</Text>
            </Pressable>
          </View>
          {provider ? <Text style={styles.muted}>{provider} · tabela z {effectiveDate}</Text> : null}
          {ratesInPreferredCurrency.filter(rate => rate.currency_code !== preferredCurrency).map(rate => (
            <View key={rate.currency_code} style={styles.rateRow}>
              <Text style={styles.rateCurrency}>1 {rate.currency_code}</Text>
              <Text style={styles.rateValue}>{rate.value === null ? '—' : `${formatExchangeRate(rate.value)} ${preferredCurrency}`}</Text>
            </View>
          ))}
          <Text style={styles.muted}>Przeliczenie orientacyjne. Kwotę rozliczenia wylicza serwer.</Text>
        </View>

        {quote ? (
          <View style={styles.formCard}>
            <Text style={styles.sectionTitle}>Potwierdź wymianę</Text>
            <View style={styles.quoteAmount}>
              <Text style={styles.muted}>Oddasz</Text>
              <Text style={styles.quoteBig}>{quote.source_amount} {quote.source_currency_code}</Text>
            </View>
            <ArrowLeftRight size={21} color={COLORS.yellow} />
            <View style={styles.quoteAmount}>
              <Text style={styles.muted}>Otrzymasz</Text>
              <Text style={styles.quoteBig}>{quote.destination_amount} {quote.destination_currency_code}</Text>
            </View>
            <View style={styles.quoteMeta}>
              <Text style={styles.quoteMetaText}>{formatExchangeRateLabel(quote.source_currency_code, quote.exchange_rate, quote.destination_currency_code)}</Text>
              <Text style={styles.quoteMetaText}>Źródło: {quote.provider} · tabela z {quote.effective_date}</Text>
              <Text style={styles.quoteMetaText}>Wycena ważna do {new Date(quote.expires_at).toLocaleTimeString('pl-PL', {hour: '2-digit', minute: '2-digit'})}</Text>
            </View>
            {error ? <Text style={styles.error}>{error}</Text> : null}
            {isExchanging ? <ActivityIndicator color={COLORS.yellow} /> : <AppButton title="Potwierdź wymianę" onPress={executeExchange} />}
            <AppButton title="Wróć i zmień dane" onPress={invalidateQuote} secondary />
          </View>
        ) : (
          <View style={styles.formCard}>
            <Text style={styles.sectionTitle}>Przygotuj wymianę</Text>
            <Text style={styles.label}>Z rachunku</Text>
            <AccountSelector label="Wybierz rachunek źródłowy" account={sourceAccount} onPress={() => setPicker('source')} />
            <Text style={styles.label}>Na rachunek</Text>
            <AccountSelector label="Wybierz rachunek docelowy" account={destinationAccount} onPress={() => setPicker('destination')} />
            <FormInput label={`Kwota${sourceAccount ? ` (${sourceAccount.currency_code})` : ''}`} value={amount} onChangeText={value => {setAmount(value); invalidateQuote();}} keyboardType="decimal-pad" placeholder="0,00" />
            {sourceAccount && destinationAccount && sourceAmountMinor !== null ? <Text style={styles.preview}>{estimatedAmount
              ? `Orientacyjnie otrzymasz około ${estimatedAmount} ${destinationAccount.currency_code}. Dokładną kwotę pokaże wycena.`
              : 'Nie udało się obliczyć orientacyjnej kwoty. Pobierz wycenę, aby zobaczyć dokładny wynik.'}</Text> : null}
            {isQuoting ? <ActivityIndicator color={COLORS.yellow} /> : <AppButton title="Pobierz wycenę" onPress={requestQuote} />}
          </View>
        )}
      </ScrollView>

      <RatesWebViewModal visible={isSourcePageVisible} onClose={() => setSourcePageVisible(false)} />
      <Modal visible={picker !== null} transparent animationType="slide" onRequestClose={() => setPicker(null)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.pickerCard}>
            <Text style={styles.sectionTitle}>{picker === 'source' ? 'Wybierz rachunek źródłowy' : 'Wybierz rachunek docelowy'}</Text>
            <ScrollView>
              {accounts.filter(account => picker === 'source' || account.id !== sourceAccountId).map(account => (
                <Pressable key={account.id} accessibilityRole="button" onPress={() => chooseAccount(account)} style={styles.accountOption}>
                  <Text style={styles.accountText}>{account.currency_code}</Text>
                  <Text style={styles.muted}>{account.balance}</Text>
                </Pressable>
              ))}
            </ScrollView>
            <AppButton title="Anuluj" onPress={() => setPicker(null)} secondary />
          </View>
        </View>
      </Modal>
      <TransactionDetails transactionId={transactionId} token={token} onClose={() => setTransactionId(null)} goHome={goHome} />
    </>
  );
}

function AccountSelector({label, account, onPress}: {label: string; account: Account | null; onPress: () => void}) {
  return (
    <Pressable accessibilityRole="button" accessibilityLabel={label} onPress={onPress} style={styles.selector}>
      <View>
        <Text style={styles.selectorTitle}>{account?.currency_code ?? 'Wybierz rachunek'}</Text>
        {account ? <Text style={styles.selectorBalance}>Saldo: {account.balance}</Text> : null}
      </View>
      <ChevronDown size={20} color={COLORS.muted} />
    </Pressable>
  );
}

function RatesWebViewModal({visible, onClose}: {visible: boolean; onClose: () => void}) {
  return (
    <Modal visible={visible} animationType="slide" onRequestClose={onClose}>
      <SafeAreaProvider>
        <SafeAreaView style={styles.sourcePage} edges={['top', 'bottom']}>
          <View style={styles.sourcePageHeader}>
            <Text style={styles.sourcePageTitle}>Kursy walut NBP</Text>
            <Pressable accessibilityRole="button" accessibilityLabel="Zamknij kursy walut NBP" onPress={onClose} style={styles.sourcePageClose}>
              <X size={22} color={COLORS.white} />
              <Text style={styles.sourcePageCloseText}>Zamknij</Text>
            </Pressable>
          </View>
          <WebView source={{uri: 'https://nbp.pl/statystyka-i-sprawozdawczosc/kursy/tabela-a/'}} startInLoadingState javaScriptEnabled domStorageEnabled scrollEnabled nestedScrollEnabled style={styles.webView} />
        </SafeAreaView>
      </SafeAreaProvider>
    </Modal>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {flexGrow: 1, paddingHorizontal: 20, paddingTop: 16, paddingBottom: 28, gap: 16},
  ratesCard: {backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, padding: 16, gap: 10},
  sectionHeading: {flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  sectionTitle: {color: COLORS.white, fontSize: 20, fontWeight: '800'},
  sourceLink: {minWidth: 44, minHeight: 44, alignItems: 'center', justifyContent: 'center'},
  sourceLinkText: {color: COLORS.yellow, fontWeight: '700'},
  muted: {color: COLORS.muted, fontSize: 13, lineHeight: 19},
  rateRow: {borderTopWidth: 1, borderTopColor: COLORS.border, paddingVertical: 9, flexDirection: 'row', justifyContent: 'space-between'},
  rateCurrency: {color: COLORS.white, fontSize: 15, fontWeight: '700'},
  rateValue: {color: COLORS.yellow, fontSize: 15, fontWeight: '700'},
  formCard: {backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, padding: 18, gap: 13},
  label: {color: COLORS.muted, fontSize: 14, fontWeight: '600'},
  selector: {minHeight: 60, backgroundColor: COLORS.input, borderColor: COLORS.border, borderWidth: 1, borderRadius: 12, paddingHorizontal: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  selectorTitle: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
  selectorBalance: {color: COLORS.muted, fontSize: 12, marginTop: 3},
  preview: {color: COLORS.muted, fontSize: 13},
  quoteAmount: {alignSelf: 'stretch', gap: 4},
  quoteBig: {color: COLORS.white, fontSize: 25, fontWeight: '800'},
  quoteMeta: {alignSelf: 'stretch', borderTopWidth: 1, borderTopColor: COLORS.border, paddingTop: 12, gap: 8},
  quoteMetaText: {color: COLORS.muted, fontSize: 14},
  error: {color: '#FCA5A5', fontSize: 14, lineHeight: 20},
  sourcePage: {flex: 1, backgroundColor: COLORS.background},
  sourcePageHeader: {minHeight: 64, backgroundColor: COLORS.surface, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: COLORS.border},
  sourcePageTitle: {color: COLORS.white, fontSize: 18, fontWeight: '700'},
  sourcePageClose: {minWidth: 88, minHeight: 44, paddingHorizontal: 8, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 4},
  sourcePageCloseText: {color: COLORS.white, fontSize: 14, fontWeight: '700'},
  webView: {flex: 1, backgroundColor: '#FFFFFF'},
  modalBackdrop: {flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(0,0,0,0.7)', padding: 16},
  pickerCard: {maxHeight: '75%', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 18, padding: 20, gap: 14},
  accountOption: {minHeight: 56, borderBottomWidth: 1, borderBottomColor: COLORS.border, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between'},
  accountText: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
}));
