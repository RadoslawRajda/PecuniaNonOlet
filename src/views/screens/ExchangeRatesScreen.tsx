import React, {useCallback, useEffect} from 'react';
import {
  Modal,
  PermissionsAndroid,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import Geolocation from 'react-native-geolocation-service';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';
import type {BackScreenProps} from '../../types/BackScreenProps';

const MANUAL_COUNTRIES = [
  'Polska',
  'Niemcy',
  'Czechy',
  'Słowacja',
  'Wielka Brytania',
  'Stany Zjednoczone',
];

export function ExchangeRatesScreen({onBack}: BackScreenProps) {
  const [country, setCountry] = React.useState<string | null>(null);
  const [isCountryPickerVisible, setCountryPickerVisible] = React.useState(false);

  const chooseCountryManually = useCallback(() => {
    setCountryPickerVisible(true);
  }, []);

  const getCountryFromLocation = useCallback(async (
    latitude: number,
    longitude: number,
  ) => {
    const response = await fetch(
      `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latitude}&longitude=${longitude}&localityLanguage=pl`,
    );

    if (!response.ok) {
      throw new Error(`Reverse geocoding failed with status ${response.status}`);
    }

    const data: {countryName?: string} = await response.json();
    if (!data.countryName) {
      throw new Error('Reverse geocoding returned no country');
    }

    setCountry(data.countryName);
  }, []);

  const readCurrentLocation = useCallback(() => {
    Geolocation.getCurrentPosition(
      position => {
        getCountryFromLocation(
          position.coords.latitude,
          position.coords.longitude,
        ).catch(error => {
          console.error('Nie udało się ustalić państwa:', error);
          chooseCountryManually();
        });
      },
      error => {
        console.error('Nie udało się pobrać lokalizacji:', error);
        chooseCountryManually();
      },
      {
        enableHighAccuracy: false,
        timeout: 10000,
        maximumAge: 300000,
      },
    );
  }, [chooseCountryManually, getCountryFromLocation]);

  useEffect(() => {
    async function requestLocationPermission() {
      try {
        if (Platform.OS === 'ios') {
          const status = await Geolocation.requestAuthorization('whenInUse');

          if (status === 'granted') {
            readCurrentLocation();
          } else {
            chooseCountryManually();
          }

          return;
        }

        const permission = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.ACCESS_COARSE_LOCATION,
        );
        const hasAccess =
          permission === PermissionsAndroid.RESULTS.GRANTED;

        if (hasAccess) {
          readCurrentLocation();
        } else {
          chooseCountryManually();
        }
      } catch (error) {
        console.error('Nie udało się poprosić o dostęp do lokalizacji:', error);
        chooseCountryManually();
      }
    }

    requestLocationPermission();
  }, [chooseCountryManually, readCurrentLocation]);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />

        <Text style={styles.title}>Kurs wymiany walut</Text>

        <Text style={styles.countryLabel}>Obecny kraj</Text>
        <Text style={styles.country}>{country ?? 'Ustalanie...'}</Text>

        <View style={styles.buttons}>
          <AppButton
            title="Wróć do dashboardu"
            onPress={onBack}
            secondary
          />
        </View>
      </View>

      <Modal
        visible={isCountryPickerVisible}
        transparent
        animationType="fade"
        onRequestClose={() => setCountryPickerVisible(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalCard}>
            <Text style={styles.modalTitle}>Wybierz państwo</Text>
            <Text style={styles.modalDescription}>
              Wybierz państwo, które ma być używane do kursów walut.
            </Text>

            {MANUAL_COUNTRIES.map(countryName => (
              <Pressable
                key={countryName}
                accessibilityRole="button"
                onPress={() => {
                  setCountry(countryName);
                  setCountryPickerVisible(false);
                }}
                style={({pressed}) => [
                  styles.countryOption,
                  pressed && styles.pressed,
                ]}>
                <Text style={styles.countryOptionText}>{countryName}</Text>
              </Pressable>
            ))}
          </View>
        </View>
      </Modal>
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
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(0, 0, 0, 0.65)',
    justifyContent: 'center',
    padding: 24,
  },
  modalCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 16,
    padding: 22,
  },
  modalTitle: {
    color: COLORS.white,
    fontSize: 22,
    fontWeight: '700',
  },
  modalDescription: {
    color: COLORS.muted,
    fontSize: 15,
    marginTop: 8,
    marginBottom: 16,
  },
  countryOption: {
    borderTopWidth: 1,
    borderTopColor: COLORS.border,
    paddingVertical: 14,
  },
  countryOptionText: {
    color: COLORS.white,
    fontSize: 17,
  },
  pressed: {
    opacity: 0.7,
  },
});
