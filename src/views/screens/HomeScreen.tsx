import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onLogin: () => void;
  onRegister: () => void;
};

export function HomeScreen({onLogin, onRegister}: Props) {
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />

        <Text style={styles.title}>
          Pecunia non olet
        </Text>

        <Text style={styles.subtitle}>
          Turbo bank
        </Text>

        <Text style={styles.description}>
          Twoje pieniądze. Twoje zasady.
        </Text>

        <View style={styles.buttons}>
          <AppButton
            title="Zaloguj się"
            onPress={onLogin}
          />

          <AppButton
            title="Załóż konto"
            onPress={onRegister}
            secondary
          />
        </View>
      </View>

      <View style={styles.footer}>
        <Text style={styles.footerTitle}>Autorzy</Text>

        <Text style={styles.authors}>
          Radosław Rajda{'\n'}
          Jakub Gnela{'\n'}
          Jakub Knapik
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingBottom: 28,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 55,
  },
  title: {
    color: COLORS.yellow,
    fontSize: 34,
    fontWeight: '800',
    textAlign: 'center',
    marginTop: 30,
  },
  subtitle: {
    color: COLORS.white,
    fontSize: 20,
    marginTop: 10,
  },
  description: {
    color: COLORS.muted,
    fontSize: 15,
    textAlign: 'center',
    marginTop: 12,
  },
  buttons: {
    width: '100%',
    marginTop: 48,
    gap: 14,
  },
  footer: {
    alignItems: 'center',
  },
  footerTitle: {
    color: COLORS.yellow,
    fontSize: 15,
    fontWeight: '700',
    marginBottom: 10,
  },
  authors: {
    color: COLORS.muted,
    fontSize: 14,
    lineHeight: 24,
    textAlign: 'center',
  },
});