import React, {useCallback, useRef, useState} from 'react';
import {
  KeyboardAvoidingView,
  Keyboard,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {AppButton, FormInput} from '../components/Ui';
import {TurnstileCaptcha} from '../components/TurnstileCaptcha';
import {COLORS, createThemedStyles} from '../theme';
import type {RegisterScreenProps} from '../../types/RegisterScreenProps';
import {validateRegister} from '../../models/auth';

export function RegisterScreen({
  onBack,
  onLogin,
  onSubmit,
}: RegisterScreenProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [captchaToken, setCaptchaToken] = useState('');
  const [captchaResetKey, setCaptchaResetKey] = useState(0);
  const scrollView = useRef<ScrollView>(null);
  const handleCaptchaToken = useCallback((token: string) => setCaptchaToken(token), []);

  const revealFocusedInput = (nativeEvent: {target: number}) => {
    scrollView.current?.scrollResponderScrollNativeHandleToKeyboard(
      nativeEvent.target,
      24,
      true,
    );
  };

  const submit = () => {
    const data = {email, password, confirmPassword, captchaToken};
    if (!captchaToken) return;
    if (validateRegister(data)) {
      onSubmit(data);
      return;
    }
    onSubmit(data);
    setCaptchaToken('');
    setCaptchaResetKey(key => key + 1);
  };

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}>

      <ScrollView
        ref={scrollView}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="interactive"
        contentContainerStyle={styles.scroll}>

        <Pressable
          accessibilityRole="button"
          onPress={onBack}
          style={styles.backButton}>
          <Text style={styles.backText}>← Wróć</Text>
        </Pressable>

        <Text style={styles.title}>Załóż konto</Text>

        <Text style={styles.subtitle}>
          Dołącz do Pecunia non olet.
        </Text>

        <View style={styles.form}>
          <FormInput
            label="Adres e-mail"
            placeholder="Wpisz adres e-mail"
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="email"
            returnKeyType="next"
            onFocus={event => revealFocusedInput(event.nativeEvent)}
            onSubmitEditing={() => Keyboard.dismiss()}
          />

          <FormInput
            label="Hasło"
            placeholder="Minimum 8 znaków"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
            returnKeyType="next"
            onFocus={event => revealFocusedInput(event.nativeEvent)}
            onSubmitEditing={() => Keyboard.dismiss()}
          />

          <FormInput
            label="Powtórz hasło"
            placeholder="Wpisz hasło ponownie"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            autoComplete="new-password"
            returnKeyType="done"
            onFocus={event => revealFocusedInput(event.nativeEvent)}
            onSubmitEditing={() => Keyboard.dismiss()}
          />

          <TurnstileCaptcha onToken={handleCaptchaToken} resetKey={captchaResetKey} />

          <AppButton
            title={captchaToken ? 'Utwórz konto' : 'Potwierdź CAPTCHA'}
            onPress={submit}
          />
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Masz już konto?{' '}
          </Text>

          <Pressable
            accessibilityRole="button"
            onPress={onLogin}>
            <Text style={styles.link}>Zaloguj się</Text>
          </Pressable>
        </View>

      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 8,
    paddingBottom: 24,
  },
  backButton: {
    alignSelf: 'flex-start',
    paddingVertical: 8,
  },
  backText: {
    color: COLORS.white,
    fontSize: 17,
  },
  title: {
    color: COLORS.white,
    fontSize: 36,
    fontWeight: '800',
    marginTop: 15,
  },
  subtitle: {
    color: COLORS.muted,
    fontSize: 16,
    marginTop: 12,
    marginBottom: 18,
  },
  form: {
    gap: 12,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    flexWrap: 'wrap',
    marginTop: 20,
  },
  footerText: {
    color: COLORS.muted,
    fontSize: 16,
  },
  link: {
    color: COLORS.yellow,
    fontSize: 16,
    fontWeight: '600',
  },
}));
