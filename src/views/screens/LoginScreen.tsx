import React, {useState} from 'react';
import {
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {AppButton, FormInput} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import type {LoginScreenProps} from '../../types/LoginScreenProps';

export function LoginScreen({
  onBack,
  onRegister,
  onSubmit,
  onPasskey,
  onGoogle,
  mfaRequired,
  onSubmitMfa,
  onCancelMfa,
}: LoginScreenProps) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');

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
          {mfaRequired ? (
            <>
              <Text style={styles.subtitle}>Wpisz kod z aplikacji Authenticator lub kod odzyskiwania.</Text>
              <View style={styles.codeField}>
                <Text style={styles.codeLabel}>Kod uwierzytelniający</Text>
                <View style={styles.codeEntry}>
                  <View pointerEvents="none" style={styles.codeBoxes}>
                    {Array.from({length: 6}, (_, index) => (
                      <View key={index} style={styles.codeBox}>
                        <Text style={styles.codeDigit}>{code[index] ?? ''}</Text>
                      </View>
                    ))}
                  </View>
                  <TextInput
                    accessibilityLabel="Kod uwierzytelniający"
                    accessibilityHint="Wpisz sześciocyfrowy kod z aplikacji Authenticator"
                    value={code}
                    onChangeText={value => setCode(value.replace(/\D/g, '').slice(0, 6))}
                    keyboardType="number-pad"
                    maxLength={6}
                    autoCorrect={false}
                    selectionColor={COLORS.yellow}
                    style={styles.codeInput}
                  />
                </View>
              </View>
              <AppButton title="Potwierdź kod" onPress={() => onSubmitMfa?.(code)} />
              <AppButton title="Wróć do logowania" onPress={onCancelMfa ?? onBack} secondary />
            </>
          ) : null}
          {!mfaRequired ? <>
          <FormInput
            label="Login lub e-mail"
            placeholder="Wpisz login lub e-mail"
            value={email}
            onChangeText={setEmail}
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
              onSubmit({email, password})
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
          <AppButton title="Zaloguj przez Google" onPress={onGoogle} secondary />
          </> : null}
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

const styles = createThemedStyles(() => StyleSheet.create({
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
  codeField: {
    gap: 9,
  },
  codeLabel: {
    color: COLORS.muted,
    fontSize: 15,
    fontWeight: '500',
  },
  codeEntry: {
    height: 58,
    position: 'relative',
    justifyContent: 'center',
  },
  codeBoxes: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: 8,
  },
  codeBox: {
    flex: 1,
    height: 58,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: COLORS.input,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  codeDigit: {
    color: COLORS.white,
    fontSize: 22,
    fontWeight: '600',
  },
  codeInput: {
    ...StyleSheet.absoluteFill,
    color: 'transparent',
    fontSize: 22,
    opacity: 0.02,
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
}));
