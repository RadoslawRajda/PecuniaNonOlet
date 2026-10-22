import React, {useState} from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type {RegisterData} from '../../models/auth';
import {AppButton, FormInput} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onBack: () => void;
  onLogin: () => void;
  onSubmit: (data: RegisterData) => void;
};

export function RegisterScreen({
  onBack,
  onLogin,
  onSubmit,
}: Props) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');

  return (
    <KeyboardAvoidingView
      style={styles.container}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}>

      <ScrollView
        keyboardShouldPersistTaps="handled"
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
          />

          <FormInput
            label="Hasło"
            placeholder="Minimum 8 znaków"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="new-password"
          />

          <FormInput
            label="Powtórz hasło"
            placeholder="Wpisz hasło ponownie"
            value={confirmPassword}
            onChangeText={setConfirmPassword}
            secureTextEntry
            autoComplete="new-password"
          />

          <AppButton
            title="Utwórz konto"
            onPress={() =>
              onSubmit({
                email,
                password,
                confirmPassword,
              })
            }
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

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  scroll: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 50,
  },
  backButton: {
    alignSelf: 'flex-start',
    paddingVertical: 12,
  },
  backText: {
    color: COLORS.white,
    fontSize: 17,
  },
  title: {
    color: COLORS.white,
    fontSize: 36,
    fontWeight: '800',
    marginTop: 45,
  },
  subtitle: {
    color: COLORS.muted,
    fontSize: 16,
    marginTop: 12,
    marginBottom: 38,
  },
  form: {
    gap: 20,
  },
  footer: {
    flexDirection: 'row',
    justifyContent: 'center',
    flexWrap: 'wrap',
    marginTop: 42,
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
});