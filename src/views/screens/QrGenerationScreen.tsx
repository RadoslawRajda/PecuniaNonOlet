import React, {useEffect, useState} from 'react';
import {ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View} from 'react-native';
import QRCode from 'react-native-qrcode-svg';
import {API_URL} from '@env';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import type {Account} from '../../types/Account';
import {useAppPreferences} from '../../context/AppPreferences';

type QrPaymentProps = {
  username: string;
  token: string | null;
  onBack: () => void;
};

export function QrGenerationScreen({username, token, onBack}: QrPaymentProps) {
  const {preferredCurrency} = useAppPreferences();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [selectedCurrency, setSelectedCurrency] = useState('');
  const [loading, setLoading] = useState(true);
  const [amount, setAmount] = useState('');
  const [showQr, setShowQr] = useState(false);
  const normalizedAmount = amount.trim().replace(',', '.');
  const validAmount = /^\d+(\.\d{1,2})?$/.test(normalizedAmount) && Number(normalizedAmount) > 0;
  const validEmail = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(username.trim());
  const canGenerate = validEmail && Boolean(selectedCurrency) && validAmount;
  const paymentData = JSON.stringify({
    type: 'pecunia-payment',
    version: 1,
    recipient_email: username.trim().toLowerCase(),
    currency_code: selectedCurrency,
    amount: normalizedAmount,
  });

  useEffect(() => {
    if (!token) {
      setLoading(false);
      return;
    }
    fetch(`${(API_URL ?? '').trim().replace(/\/+$/, '')}/api/accounts`, {
      headers: {Authorization: `Bearer ${token}`},
    })
      .then(response => response.json())
      .then(data => {
        const userAccounts = data?.accounts ?? [];
        setAccounts(userAccounts);
        setSelectedCurrency(userAccounts.find((account: Account) => account.currency_code === preferredCurrency)?.currency_code ?? userAccounts[0]?.currency_code ?? '');
      })
      .catch(error => console.error('Nie udało się pobrać kont:', error))
      .finally(() => setLoading(false));
  }, [preferredCurrency, token]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />
        <Text style={styles.title}>Odbierz płatność</Text>
        <Text style={styles.description}>
          Wybierz konto i kwotę, a następnie pokaż kod QR płatnikowi.
        </Text>
        <Text style={styles.email}>{username}</Text>

        {loading ? <ActivityIndicator color={COLORS.yellow} /> : null}
        <Text style={styles.label}>Konto do wpłaty</Text>
        <View style={styles.accounts}>
          {accounts.map(account => (
            <Pressable
              key={account.id}
              accessibilityRole="button"
              accessibilityState={{selected: selectedCurrency === account.currency_code}}
              onPress={() => {
                setSelectedCurrency(account.currency_code);
                setShowQr(false);
              }}
              style={[styles.account, selectedCurrency === account.currency_code && styles.selectedAccount]}>
              <Text style={styles.currency}>{account.currency_code}</Text>
              <Text style={styles.balance}>{account.balance}</Text>
            </Pressable>
          ))}
        </View>

        <Text style={styles.label}>Kwota</Text>
        <TextInput
          accessibilityLabel="Kwota"
          value={amount}
          onChangeText={value => {
            setAmount(value);
            setShowQr(false);
          }}
          placeholder="np. 25.00"
          placeholderTextColor={COLORS.muted}
          keyboardType="decimal-pad"
          style={styles.input}
        />
        <View style={styles.button}>
          <AppButton title="Wygeneruj kod QR" onPress={() => setShowQr(true)} />
        </View>
        {!canGenerate && amount.length > 0 ? (
          <Text style={styles.hint}>Podaj poprawną kwotę większą od zera.</Text>
        ) : null}
        {showQr && canGenerate ? (
          <View style={styles.qrCard}>
            <QRCode value={paymentData} size={230} />
            <Text style={styles.qrAmount}>{normalizedAmount} {selectedCurrency}</Text>
            <Text style={styles.qrEmail}>{username}</Text>
          </View>
        ) : null}

        <View style={styles.button}>
          <AppButton title="Wróć do dashboardu" onPress={onBack} secondary />
        </View>
      </View>
    </ScrollView>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {flexGrow: 1, paddingHorizontal: 24, paddingVertical: 20},
  content: {flexGrow: 1, alignItems: 'center', paddingVertical: 35},
  title: {color: COLORS.yellow, fontSize: 30, fontWeight: '800', textAlign: 'center', marginTop: 30},
  description: {color: COLORS.muted, fontSize: 15, textAlign: 'center', marginTop: 12},
  email: {color: COLORS.white, fontSize: 16, marginTop: 18},
  label: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 15, fontWeight: '600', marginTop: 24},
  accounts: {alignSelf: 'stretch', gap: 8, marginTop: 10},
  account: {backgroundColor: COLORS.surface, borderColor: COLORS.border, borderRadius: 12, borderWidth: 1, padding: 14, flexDirection: 'row', justifyContent: 'space-between'},
  selectedAccount: {borderColor: COLORS.yellow},
  currency: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
  balance: {color: COLORS.muted},
  input: {alignSelf: 'stretch', height: 56, backgroundColor: COLORS.input, borderColor: COLORS.border, borderRadius: 12, borderWidth: 1, color: COLORS.white, fontSize: 17, marginTop: 10, paddingHorizontal: 16},
  button: {width: '100%', marginTop: 24},
  qrCard: {alignItems: 'center', backgroundColor: '#FFFFFF', borderRadius: 16, marginTop: 28, padding: 18},
  qrAmount: {color: '#111827', fontSize: 18, fontWeight: '800', marginTop: 14},
  qrEmail: {color: '#374151', fontSize: 13, marginTop: 4},
  hint: {color: '#FCA5A5', marginTop: 12},
}));
