import React from 'react';
import {StyleSheet, Text, View} from 'react-native';
import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
type Props = {onScan: () => void; onCreate: () => void};

export function QrHubScreen({onScan, onCreate}: Props) {
  return (
    <View style={styles.container}>
      <BrandLogo />
      <Text style={styles.title}>Kod QR</Text>
      <Text style={styles.description}>Wybierz, co chcesz zrobić.</Text>
      <View style={styles.actions}>
        <AppButton title="Skanuj kod" onPress={onScan} />
        <AppButton title="Utwórz kod do wpłaty" onPress={onCreate} secondary />
      </View>
    </View>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, backgroundColor: COLORS.background},
  title: {color: COLORS.yellow, fontSize: 30, fontWeight: '800', marginTop: 24},
  description: {color: COLORS.muted, fontSize: 15, marginTop: 8},
  actions: {width: '100%', gap: 14, marginTop: 32},
}));
