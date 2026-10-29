import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  Pressable,
  View,
} from 'react-native';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onBack: () => void;
  onLogout: () => void;
  username: string;    
};

export function Dashboard({onBack, onLogout, username}: Props) {
  return (
    <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.content}>
            <BrandLogo />

            <Text style={styles.title}>
            Dashboard
            </Text>

            <Text style={styles.subtitle}>
            Panel użytkownika
            </Text>

            <Text style={styles.description}>
            Jesteś Zalogowany jako {username} :D
            </Text>

            {/* Kontener na przyciski */}
            <View style={styles.buttons}>
              <AppButton 
                title="Wyloguj się" 
                onPress={onLogout} 
              />
            </View>
        </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingTop: 20,
    paddingBottom: 28,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 35,
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
  backButton: {
    alignSelf: 'flex-start',
    paddingVertical: 12,
  },
  backText: {
    color: COLORS.white,
    fontSize: 17,
  },
});