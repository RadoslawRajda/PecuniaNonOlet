import React, {useEffect} from 'react';
import {
  Alert,
  PermissionsAndroid,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Geolocation from 'react-native-geolocation-service';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onBack: () => void;
};

export function ExchangeRatesScreen({onBack}: Props) {
  useEffect(() => {
    async function requestLocationPermission() {
      try {
        if (Platform.OS === 'ios') {
          const status = await Geolocation.requestAuthorization('whenInUse');

          if (status !== 'granted') {
            Alert.alert(
              'Dostęp do lokalizacji',
              'Aby automatycznie ustawić walutę, zezwól aplikacji na dostęp do lokalizacji.',
            );
          }

          return;
        }

        const permission = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION,
        );
        const hasAccess =
          permission === PermissionsAndroid.RESULTS.GRANTED;

        if (!hasAccess) {
          Alert.alert(
            'Dostęp do lokalizacji',
            'Aby automatycznie ustawić walutę, zezwól aplikacji na dostęp do lokalizacji.',
          );
        }
      } catch (error) {
        console.error('Nie udało się poprosić o dostęp do lokalizacji:', error);
        Alert.alert(
          'Dostęp do lokalizacji',
          'Nie udało się poprosić o dostęp do lokalizacji.',
        );
      }
    }

    requestLocationPermission();
  }, []);

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
