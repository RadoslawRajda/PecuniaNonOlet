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

import type {LoginData} from '../../models/auth';
import {AppButton, FormInput} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onBack: () => void;
  onRegister: () => void;
  onSubmit: (data: LoginData) => void;
  onPasskey: () => void;
};

export function LoginScreen({
  onBack,
  onRegister,
  onSubmit,
  onPasskey,
}: Props) {
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');

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

        <Text style={styles.title}>Zaloguj się</Text>

        <Text style={styles.subtitle}>
          Witaj ponownie w Pecunia non olet.
        </Text>

        <View style={styles.form}>
          <FormInput
            label="Login lub e-mail"
            placeholder="Wpisz login lub e-mail"
            value={identifier}
            onChangeText={setIdentifier}
            autoCapitalize="none"
            autoCorrect={false}
            autoComplete="username"
          />

          <FormInput
            label="Hasło"
            placeholder="Wpisz hasło"
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            autoComplete="current-password"
          />

          <AppButton
            title="Zaloguj się"
            onPress={() =>
              onSubmit({identifier, password})
            }
          />

          <View style={styles.separator}>
            <View style={styles.line} />
            <Text style={styles.orText}>lub</Text>
            <View style={styles.line} />
          </View>

          <AppButton
            title="Zaloguj przez passkey"
            onPress={onPasskey}
            secondary
          />
        </View>

        <View style={styles.footer}>
          <Text style={styles.footerText}>
            Nie masz konta?{' '}
          </Text>

          <Pressable
            accessibilityRole="button"
            onPress={onRegister}>
            <Text style={styles.link}>Załóż konto</Text>
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
  separator: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 16,
    marginVertical: 5,
  },
  line: {
    height: 1,
    backgroundColor: COLORS.border,
    flex: 1,
  },
  orText: {
    color: COLORS.muted,
    fontSize: 16,
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