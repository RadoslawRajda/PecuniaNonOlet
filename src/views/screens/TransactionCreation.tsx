import React from 'react';
import {
  ActivityIndicator,
  Animated,
  Dimensions,
  Easing,
  KeyboardAvoidingView,
  Modal,
  Pressable,
  Platform,
  PanResponder,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {API_URL} from '@env';
import {useSafeAreaInsets} from 'react-native-safe-area-context';

import {AppButton, FormInput} from '../components/Ui';
import {CounterpartyAvatar} from '../components/CounterpartyAvatar';
import {COLORS, createThemedStyles} from '../theme';
import type {TransactionCreationProps} from '../../types/TransactionCreationProps';
import type {TransactionCreationFormValues} from '../../types/TransactionCreationFormValues';
import {handleForbiddenResponse, useAppPreferences} from '../../context/AppPreferences';
import LockKeyhole from 'lucide-react-native/icons/lock-keyhole';
import LockKeyholeOpen from 'lucide-react-native/icons/lock-keyhole-open';

export function TransactionCreation({
  visible,
  token,
  accounts,
  initialValues,
  onClose,
  onCreated,
}: TransactionCreationProps) {
  const {preferredCurrency, handleForbidden} = useAppPreferences();
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
  const [isSendingAnimation, setIsSendingAnimation] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [swipeTrackWidth, setSwipeTrackWidth] = React.useState(0);

  React.useEffect(() => {
    if (visible) {
      setValues({
        recipientEmail: initialValues?.recipientEmail ?? '',
        account: initialValues?.account ?? accounts.find(account => account.currency_code === preferredCurrency) ?? accounts[0] ?? null,
        amount: initialValues?.amount ?? '',
      });
      setIsReviewing(false);
      setError(null);
    }
  }, [accounts, initialValues, preferredCurrency, visible]);

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

  const submitTransaction = React.useCallback(async () => {
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
      if (handleForbiddenResponse(response, handleForbidden)) return;
      const data = await response.json().catch(() => null);
      if (!response.ok) {
        throw new Error(data?.detail || 'Nie udało się utworzyć transakcji.');
      }
      onCreated(data?.transaction_id);
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
  }, [apiBaseUrl, onClose, onCreated, token, values]);

  const swipePosition = React.useRef(new Animated.Value(0)).current;
  const swipeScale = React.useRef(new Animated.Value(1)).current;
  const swipeInProgress = React.useRef(false);
  const swipeTravel = Math.max(0, swipeTrackWidth - 64);
  const sheetHeight = Dimensions.get('window').height;
  const sheetPosition = React.useRef(new Animated.Value(sheetHeight)).current;
  const sendingTimeout = React.useRef<ReturnType<typeof setTimeout> | null>(null);
  React.useEffect(() => {
    if (!visible) return;
    sheetPosition.setValue(sheetHeight);
    swipePosition.setValue(0);
    swipeScale.setValue(1);
    swipeInProgress.current = false;
    setIsSendingAnimation(false);
    Animated.spring(sheetPosition, {toValue: 0, useNativeDriver: true, speed: 18, bounciness: 2}).start();
  }, [sheetHeight, sheetPosition, swipePosition, swipeScale, visible]);
  React.useEffect(() => () => {
    if (sendingTimeout.current) clearTimeout(sendingTimeout.current);
  }, []);

  const swipeResponder = React.useMemo(() => PanResponder.create({
    onStartShouldSetPanResponder: () => !isSubmitting && !isSendingAnimation && !swipeInProgress.current && swipeTravel > 0,
    onMoveShouldSetPanResponder: (_event, gesture) => Math.abs(gesture.dx) > 5,
    onPanResponderMove: (_event, gesture) => swipePosition.setValue(Math.max(0, Math.min(gesture.dx, swipeTravel))),
    onPanResponderRelease: (_event, gesture) => {
      if (swipeTravel > 0 && gesture.dx >= swipeTravel * 0.78) {
        swipeInProgress.current = true;
        Animated.timing(swipePosition, {toValue: swipeTravel, duration: 260, easing: Easing.out(Easing.cubic), useNativeDriver: true}).start(() => {
          setIsSendingAnimation(true);
          Animated.sequence([
            Animated.spring(swipeScale, {toValue: 1.12, useNativeDriver: true, speed: 24, bounciness: 7}),
            Animated.spring(swipeScale, {toValue: 1, useNativeDriver: true, speed: 20, bounciness: 5}),
          ]).start();
          sendingTimeout.current = setTimeout(() => {
            submitTransaction().finally(() => {
              swipeInProgress.current = false;
              swipePosition.setValue(0);
              setIsSendingAnimation(false);
            });
            sendingTimeout.current = null;
          }, 650);
        });
      } else {
        swipeInProgress.current = false;
        Animated.spring(swipePosition, {toValue: 0, useNativeDriver: true, speed: 22, bounciness: 4}).start();
      }
    },
    onPanResponderTerminate: () => {
      swipeInProgress.current = false;
      Animated.spring(swipePosition, {toValue: 0, useNativeDriver: true}).start();
    },
  }), [isSendingAnimation, isSubmitting, swipePosition, swipeScale, swipeTravel, submitTransaction]);
  const closeSheet = () => {
    if (sendingTimeout.current) clearTimeout(sendingTimeout.current);
    sendingTimeout.current = null;
    swipeInProgress.current = false;
    swipePosition.stopAnimation();
    swipePosition.setValue(0);
    swipeScale.setValue(1);
    setIsSendingAnimation(false);
    onClose();
  };

  return (
    <Modal
      visible={visible}
      transparent
      animationType="fade"
      onRequestClose={closeSheet}>
      <KeyboardAvoidingView
        style={styles.keyboardAvoidingView}
        behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>
        <View style={styles.backdrop}>
          <Pressable accessibilityRole="button" accessibilityLabel="Zamknij okno" onPress={closeSheet} style={StyleSheet.absoluteFill} />
          <Animated.View
            style={[
              styles.card,
              {paddingBottom: Math.max(24, insets.bottom + 16)},
              {transform: [{translateY: sheetPosition}]},
            ]}>
          <Text style={styles.title}>
            {isReviewing ? 'Potwierdź transakcję' : 'Nowa transakcja'}
          </Text>

            {isReviewing ? (
              <ScrollView
                keyboardShouldPersistTaps="handled"
                contentContainerStyle={styles.review}>
              <View style={styles.recipient}>
                <CounterpartyAvatar email={values.recipientEmail.trim().toLowerCase()} token={token} />
                <View style={styles.recipientInfo}>
                  <Text style={styles.label}>Wysyłasz środki do</Text>
                  <Text style={styles.value}>{values.recipientEmail.trim().toLowerCase()}</Text>
                </View>
              </View>
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
              <View style={styles.sendingState}>
                <ActivityIndicator color={COLORS.yellow} />
                <Text style={styles.sendingText}>Wysyłanie przelewu…</Text>
              </View>
            ) : isReviewing ? (
              <>
                <View style={styles.swipeContainer}>
                  <Text style={styles.swipeLabel}>{isSendingAnimation ? 'Blokada zdjęta. Wysyłam…' : 'Przesuń, aby wysłać przelew'}</Text>
                  <View style={styles.swipeTrack} onLayout={event => setSwipeTrackWidth(event.nativeEvent.layout.width)}>
                    <Animated.View style={[styles.swipeThumb, isSendingAnimation && styles.swipeThumbUnlocked, {transform: [{translateX: swipePosition}, {scale: swipeScale}]}]} {...swipeResponder.panHandlers}>
                      {isSendingAnimation ? <LockKeyholeOpen size={22} color={COLORS.darkText} /> : <LockKeyhole size={22} color={COLORS.darkText} />}
                    </Animated.View>
                    <Text pointerEvents="none" style={styles.swipeHint}>{isSendingAnimation ? 'Potwierdzono' : 'Przesuń w prawo'}</Text>
                  </View>
                </View>
                <AppButton
                  title="Wróć do edycji"
                  onPress={() => setIsReviewing(false)}
                  secondary
                />
              </>
            ) : (
              <AppButton title="Przejdź do podsumowania" onPress={reviewTransaction} />
            )}
            <AppButton title="Anuluj" onPress={closeSheet} secondary />
          </Animated.View>
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

const styles = createThemedStyles(() => StyleSheet.create({
  backdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'flex-end',
    overflow: 'hidden',
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
  recipient: {flexDirection: 'row', alignItems: 'center', gap: 12, paddingBottom: 12, borderBottomWidth: 1, borderBottomColor: COLORS.border},
  recipientInfo: {flex: 1, gap: 4},
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
  swipeContainer: {gap: 8},
  swipeLabel: {color: COLORS.white, fontSize: 15, fontWeight: '700', textAlign: 'center'},
  swipeTrack: {height: 58, borderRadius: 14, backgroundColor: COLORS.input, borderWidth: 1, borderColor: COLORS.border, justifyContent: 'center', overflow: 'hidden'},
  swipeThumb: {position: 'absolute', left: 3, top: 3, bottom: 3, width: 58, borderRadius: 11, backgroundColor: COLORS.yellow, alignItems: 'center', justifyContent: 'center', zIndex: 1},
  swipeThumbUnlocked: {backgroundColor: '#34D399'},
  swipeHint: {color: COLORS.muted, fontSize: 14, fontWeight: '600', textAlign: 'center'},
  sendingState: {minHeight: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12},
  sendingText: {color: COLORS.white, fontSize: 15, fontWeight: '700'},
  errorText: {
    color: '#FCA5A5',
    fontSize: 14,
  },
}));
