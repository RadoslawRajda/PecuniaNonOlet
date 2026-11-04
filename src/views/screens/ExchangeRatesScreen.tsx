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
  onBack: () => void;
};

export function ExchangeRatesScreen({onBack}: Props) {
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />

        <Text style={styles.title}>Kurs wymiany walut</Text>

        <Text style={styles.countryLabel}>Obecny kraj</Text>
        <Text style={styles.country}>Polska</Text>

        <View style={styles.buttons}>
          <AppButton
            title="Wróć do dashboardu"
            onPress={onBack}
            secondary
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
    paddingVertical: 20,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 35,
  },
  title: {
    color: COLORS.yellow,
    fontSize: 30,
    fontWeight: '800',
    textAlign: 'center',
    marginTop: 30,
  },
  countryLabel: {
    color: COLORS.muted,
    fontSize: 15,
    marginTop: 36,
  },
  country: {
    color: COLORS.white,
    fontSize: 22,
    fontWeight: '700',
    marginTop: 8,
  },
  buttons: {
    width: '100%',
    marginTop: 48,
  },
});
