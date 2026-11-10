import React from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Modal,
  Pressable,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {API_URL} from '@env';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {AppButton, FormInput} from '../components/Ui';
import {COLORS} from '../theme';
import type {TransactionCreationProps} from '../../types/TransactionCreationProps';
import type {TransactionCreationFormValues} from '../../types/TransactionCreationFormValues';

export function TransactionCreation({
  visible,
  token,
  accounts,
  onClose,
  onCreated,
}: TransactionCreationProps) {
  const insets = useSafeAreaInsets();
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
  const [values, setValues] = React.useState<TransactionCreationFormValues>({
    recipientEmail: '',
    account: accounts[0] ?? null,
    amount: '',
  });
  const [isAccountPickerVisible, setAccountPickerVisible] = React.useState(false);
  const [isReviewing, setIsReviewing] = React.useState(false);
  const [isSubmitting, setIsSubmitting] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (visible) {
      setValues({
        recipientEmail: '',
        account: accounts[0] ?? null,
        amount: '',
      });
      setIsReviewing(false);
      setError(null);
    }
  }, [accounts, visible]);

  const reviewTransaction = () => {
    const amount = Number(values.amount.replace(',', '.'));
    if (!values.recipientEmail.trim() || !values.recipientEmail.includes('@')) {
      setError('Podaj poprawny adres e-mail odbiorcy.');
      return;
    }
    if (!values.account) {
      setError('Wybierz rachunek źródłowy.');
      return;
    }
    if (!Number.isFinite(amount) || amount <= 0) {
      setError('Podaj poprawną kwotę większą od zera.');
      return;
    }
    if (!/^\d+([.,]\d{1,2})?$/.test(values.amount.trim())) {
      setError('Kwota może mieć maksymalnie dwa miejsca po przecinku.');
      return;
    }
    setError(null);
    setIsReviewing(true);
  };

  const submitTransaction = async () => {
    if (!token || !values.account) {
      setError('Brak aktywnej sesji lub rachunku źródłowego.');
      return;
    }

    const amountMinor = Math.round(Number(values.amount.replace(',', '.')) * 100);
    setIsSubmitting(true);
    setError(null);
    try {
      const response = await fetch(`${apiBaseUrl}/api/transfers`, {
        method: 'POST',
        headers: {
          Authorization: `Bearer ${token}`,
          'Content-Type': 'application/json',
          'Idempotency-Key': `${Date.now()}-${Math.random().toString(36).slice(2)}`,
        },
        body: JSON.stringify({
          recipient_email: values.recipientEmail.trim().toLowerCase(),
          source_account_id: values.account.id,
          currency_code: values.account.currency_code,
          amount_minor: amountMinor,
        }),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || 'Nie udało się utworzyć transakcji.');
      }
      onCreated();
      onClose();
    } catch (submitError) {
      console.error('Nie udało się utworzyć transakcji:', submitError);
      setError(
        submitError instanceof Error
          ? submitError.message
          : 'Nie udało się utworzyć transakcji.',
      );
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="slide"
      onRequestClose={onClose}>
      <KeyboardAvoidingView
        style={styles.keyboardAvoidingView}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={styles.backdrop}>
          <View
            style={[
              styles.card,
              {paddingBottom: Math.max(24, insets.bottom + 16)},
            ]}>
          <Text style={styles.title}>
            {isReviewing ? 'Potwierdź transakcję' : 'Nowa transakcja'}
          </Text>

            {isReviewing ? (
              <ScrollView
                keyboardShouldPersistTaps="handled"
                contentContainerStyle={styles.review}>
              <ReviewRow label="Odbiorca" value={values.recipientEmail} />
              <ReviewRow
                label="Rachunek źródłowy"
                value={`${values.account?.currency_code} (${values.account?.balance})`}
              />
              <ReviewRow
                label="Kwota"
                value={`${values.amount.replace(',', '.')} ${values.account?.currency_code}`}
              />
              <Text style={styles.reviewHint}>
                Sprawdź dane. Żądanie zostanie wysłane dopiero po potwierdzeniu.
              </Text>
              </ScrollView>
            ) : (
              <ScrollView
                keyboardShouldPersistTaps="handled"
                contentContainerStyle={styles.form}>
              <FormInput
                label="E-mail odbiorcy"
                value={values.recipientEmail}
                onChangeText={recipientEmail =>
                  setValues(current => ({...current, recipientEmail}))
                }
                keyboardType="email-address"
                autoCapitalize="none"
              />
              <Text style={styles.label}>Rachunek źródłowy</Text>
              <Pressable
                onPress={() => setAccountPickerVisible(current => !current)}
                style={styles.selector}>
                <Text style={styles.selectorText}>
                  {values.account
                    ? `${values.account.currency_code} - ${values.account.balance}`
                    : 'Wybierz rachunek'}
                </Text>
              </Pressable>
              {isAccountPickerVisible &&
                accounts.map(account => (
                  <Pressable
                    key={account.id}
                    onPress={() => {
                      setValues(current => ({...current, account}));
                      setAccountPickerVisible(false);
                    }}
                    style={styles.accountOption}>
                    <Text style={styles.selectorText}>
                      {account.currency_code} - {account.balance}
                    </Text>
                  </Pressable>
                ))}
              <FormInput
                label="Kwota"
                value={values.amount}
                onChangeText={amount =>
                  setValues(current => ({...current, amount}))
                }
                keyboardType="decimal-pad"
                placeholder="0.00"
              />
              </ScrollView>
            )}

            {error && <Text style={styles.errorText}>{error}</Text>}
            {isSubmitting ? (
              <ActivityIndicator color={COLORS.yellow} />
            ) : isReviewing ? (
              <>
                <AppButton title="Potwierdź i wyślij" onPress={submitTransaction} />
                <AppButton
                  title="Wróć do edycji"
                  onPress={() => setIsReviewing(false)}
                  secondary
                />
              </>
            ) : (
              <AppButton title="Przejdź do podsumowania" onPress={reviewTransaction} />
            )}
            <AppButton title="Anuluj" onPress={onClose} secondary />
          </View>
        </View>
      </KeyboardAvoidingView>
    </Modal>
  );
}

function ReviewRow({label, value}: {label: string; value: string}) {
  return (
    <View style={styles.reviewRow}>
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
  keyboardAvoidingView: {
    flex: 1,
  },
  card: {
    backgroundColor: COLORS.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 24,
    maxHeight: '90%',
    gap: 16,
  },
  title: {
    color: COLORS.white,
    fontSize: 24,
    fontWeight: '800',
  },
  form: {
    gap: 14,
    paddingBottom: 4,
  },
  review: {
    gap: 14,
    paddingBottom: 4,
  },
  reviewRow: {
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingTop: 10,
    gap: 4,
  },
  label: {
    color: COLORS.muted,
    fontSize: 14,
  },
  value: {
    color: COLORS.white,
    fontSize: 17,
  },
  selector: {
    backgroundColor: COLORS.input,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 18,
  },
  selectorText: {
    color: COLORS.white,
    fontSize: 16,
  },
  accountOption: {
    backgroundColor: COLORS.input,
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    padding: 14,
  },
  reviewHint: {
    color: COLORS.muted,
    fontSize: 14,
  },
  errorText: {
    color: '#FCA5A5',
    fontSize: 14,
  },
});
