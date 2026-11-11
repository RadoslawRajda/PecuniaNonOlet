import React from 'react';
import {
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {launchImageLibrary, type ImageLibraryOptions} from 'react-native-image-picker';
import {API_URL} from '@env';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import {useAppPreferences} from '../../context/AppPreferences';
import type {Account} from '../../types/Account';

export function ProfileScreen({onQrGeneration, onLogout}: {onQrGeneration: () => void; onLogout: () => void}) {
  const {
    token,
    colorScheme,
    setColorScheme,
    preferredCurrency,
    setPreferredCurrency,
    locationCurrencyEnabled,
    locationDetectedCurrency,
    setLocationCurrencyEnabled,
    refreshProfilePhoto,
  } = useAppPreferences();
  const [accounts, setAccounts] = React.useState<Account[]>([]);
  const [isUploading, setIsUploading] = React.useState(false);
  const [photoStatus, setPhotoStatus] = React.useState<string | null>(null);
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  React.useEffect(() => {
    if (!token) return;
    fetch(`${apiBaseUrl}/api/accounts`, {headers: {Authorization: `Bearer ${token}`}})
      .then(async response => {
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(data?.detail || 'Nie udało się pobrać rachunków.');
        setAccounts(data?.accounts ?? []);
      })
      .catch(error => console.warn('Unable to load accounts for profile settings', error));
  }, [apiBaseUrl, token]);

  async function changeProfileImage() {
    setPhotoStatus('Otwieram galerię zdjęć…');
    try {
      const options: ImageLibraryOptions = {
        mediaType: 'photo',
        selectionLimit: 1,
        assetRepresentationMode: 'compatible',
        maxWidth: 1024,
        maxHeight: 1024,
        quality: 0.8,
      };
      console.info('Profile photo picker opened');
      const result = await launchImageLibrary(options);
      if (result.didCancel) {
        console.info('Profile photo selection cancelled');
        setPhotoStatus(null);
        return;
      }
      const asset = result.assets?.[0];
      if (result.errorCode || !asset?.uri || !token) {
        throw new Error(result.errorMessage ?? 'Nie wybrano poprawnego obrazu.');
      }
      if (asset.fileSize && asset.fileSize > 2 * 1024 * 1024) {
        throw new Error('Zdjęcie może mieć maksymalnie 2 MiB.');
      }
      console.info('Profile photo selected', {type: asset.type, size: asset.fileSize});
      setPhotoStatus('Przygotowuję zdjęcie do wysłania…');

      const form = new FormData();
      form.append('file', {
        uri: asset.uri,
        name: asset.fileName ?? 'profile-photo.jpg',
        type: asset.type ?? 'image/jpeg',
      } as any);
      setIsUploading(true);
      setPhotoStatus('Wysyłam zdjęcie na serwer…');
      const response = await fetch(`${apiBaseUrl}/api/profile/photo`, {
        method: 'PUT',
        headers: {Authorization: `Bearer ${token}`},
        body: form,
      });
      console.info('Profile photo upload response', response.status);
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || `Serwer odrzucił zdjęcie (HTTP ${response.status}).`);
      }
      refreshProfilePhoto();
      setPhotoStatus('Zdjęcie profilowe zostało zapisane.');
      Alert.alert('Zdjęcie profilowe', 'Zdjęcie zostało bezpiecznie zapisane.');
    } catch (error) {
      console.error('Profile photo change failed', error);
      setPhotoStatus(error instanceof Error ? error.message : 'Wystąpił błąd podczas zmiany zdjęcia.');
      Alert.alert(
        'Nie udało się zmienić zdjęcia',
        error instanceof Error
          ? `${error.message}\nAdres: ${apiBaseUrl}/api/profile/photo`
          : `Wystąpił błąd. Adres: ${apiBaseUrl}/api/profile/photo`,
      );
    } finally {
      setIsUploading(false);
    }
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />
        <Text style={styles.title}>Profil i preferencje</Text>

        <Text style={styles.sectionTitle}>Zdjęcie profilowe</Text>
        <Text style={styles.description}>Zdjęcie jest przesyłane do prywatnego, uwierzytelnionego magazynu konta.</Text>
        <AppButton
          title={isUploading ? 'Zapisywanie zdjęcia…' : 'Zmień zdjęcie profilowe'}
          onPress={changeProfileImage}
        />
        {photoStatus ? <Text style={styles.description}>{photoStatus}</Text> : null}

        <Text style={styles.sectionTitle}>Wygląd</Text>
        <Text style={styles.description}>Aktualny motyw: {THEME_LABELS[colorScheme]}</Text>
        {THEME_OPTIONS.map(theme => (
          <Pressable
            key={theme}
            accessibilityRole="button"
            accessibilityState={{selected: colorScheme === theme}}
            onPress={() => setColorScheme(theme)}
            style={[styles.currencyOption, colorScheme === theme && styles.currencySelected]}>
            <Text style={styles.currencyText}>{THEME_LABELS[theme]}</Text>
            <Text style={styles.currencyHint}>{colorScheme === theme ? 'Wybrany motyw' : 'Ustaw motyw'}</Text>
          </Pressable>
        ))}

        {!locationCurrencyEnabled && <>
        <Text style={styles.sectionTitle}>Preferowana waluta</Text>
        <Text style={styles.description}>Używana jako domyślny wybór na dashboardzie, w przelewach i wymianie.</Text>
        {!locationCurrencyEnabled && accounts.map(account => (
          <Pressable
            key={account.id}
            accessibilityRole="button"
            accessibilityState={{selected: preferredCurrency === account.currency_code}}
            onPress={() => setPreferredCurrency(account.currency_code)}
            style={[styles.currencyOption, preferredCurrency === account.currency_code && styles.currencySelected]}>
            <Text style={styles.currencyText}>{account.currency_code}</Text>
            <Text style={styles.currencyHint}>{preferredCurrency === account.currency_code ? 'Preferowana' : 'Ustaw jako domyślną'}</Text>
          </Pressable>
        ))}

        </>}
        <Text style={styles.sectionTitle}>Waluta na podstawie lokalizacji</Text>
        <Text style={styles.description}>Po włączeniu aplikacja sprawdzi lokalizację przy logowaniu i ustawi walutę kraju.</Text>
        {locationCurrencyEnabled ? (
          <View style={[styles.currencyOption, styles.currencySelected]}>
            <Text style={styles.currencyText}>{locationDetectedCurrency ?? 'Brak wyniku'}</Text>
            <Text style={styles.currencyHint}>{locationDetectedCurrency && 'Waluta z ostatniego wyszukiwania lokalizacji'}</Text>
          </View>
        ) : null}
        <Pressable
          accessibilityRole="switch"
          accessibilityState={{checked: locationCurrencyEnabled}}
          onPress={() => setLocationCurrencyEnabled(!locationCurrencyEnabled)}
          style={[styles.currencyOption, locationCurrencyEnabled && styles.currencySelected]}>
          <Text style={styles.currencyText}>{locationCurrencyEnabled ? 'Włączona' : 'Wyłączona'}</Text>
          <Text style={styles.currencyHint}>{locationCurrencyEnabled ? 'Dotknij, aby wyłączyć' : 'Dotknij, aby włączyć'}</Text>
        </Pressable>

        <View style={styles.button}>
          <AppButton title="Wyloguj się" onPress={onLogout} secondary />
        </View>

        <View style={styles.button}>
        </View>
      </View>
    </ScrollView>
  );
}

const THEME_OPTIONS: import('../theme').ColorScheme[] = ['dark', 'light', 'pink', 'blue', 'blackAndWhite', 'highContrast'];
const THEME_LABELS: Record<import('../theme').ColorScheme, string> = {
  dark: 'Ciemny', light: 'Jasny', pink: 'Różowy', blue: 'Niebieski', blackAndWhite: 'Czarno-biały', highContrast: 'Wysoki kontrast',
};

const styles = createThemedStyles(() => StyleSheet.create({
  container: {flexGrow: 1, paddingHorizontal: 24, paddingVertical: 20},
  content: {flexGrow: 1, justifyContent: 'center', alignItems: 'center', paddingVertical: 35, gap: 12},
  title: {color: COLORS.yellow, fontSize: 30, fontWeight: '800', textAlign: 'center', marginTop: 24, marginBottom: 10},
  sectionTitle: {alignSelf: 'stretch', color: COLORS.white, fontSize: 19, fontWeight: '700', marginTop: 16},
  description: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 14, textAlign: 'center'},
  currencyOption: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderRadius: 12, borderWidth: 1, padding: 14, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center'},
  currencySelected: {borderColor: COLORS.yellow},
  currencyText: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
  currencyHint: {color: COLORS.muted, fontSize: 13},
  button: {width: '100%', marginTop: 28},
}));
