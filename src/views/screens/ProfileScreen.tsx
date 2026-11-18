import React from 'react';
import {Alert, Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';
import ChevronRight from 'lucide-react-native/icons/chevron-right';
import MapPin from 'lucide-react-native/icons/map-pin';
import Palette from 'lucide-react-native/icons/palette';
import Shield from 'lucide-react-native/icons/shield';
import CircleHelp from 'lucide-react-native/icons/circle-question-mark';
import LogOut from 'lucide-react-native/icons/log-out';
import {launchImageLibrary, type ImageLibraryOptions} from 'react-native-image-picker';
import {API_URL} from '@env';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS, createThemedStyles, type ColorScheme} from '../theme';
import {handleForbiddenResponse, useAppPreferences} from '../../context/AppPreferences';
import type {Account} from '../../types/Account';
import type {UserRole} from '../../models/auth';

type ProfilePage = 'main' | 'currency' | 'appearance' | 'account' | 'help';

export function ProfileScreen({username = 'Twoje konto', role, onLogout}: {username?: string; role: UserRole | null; onLogout: () => void}) {
  const isAnalyst = role === 'analyst';
  const {
    token, colorScheme, setColorScheme, preferredCurrency, setPreferredCurrency,
    locationCurrencyEnabled, locationDetectedCurrency, setLocationCurrencyEnabled,
    locationPermissionStatus, locationError, openLocationSettings, refreshProfilePhoto,
    retryLocationCurrency,
    handleForbidden,
  } = useAppPreferences();
  const [page, setPage] = React.useState<ProfilePage>('main');
  const [accounts, setAccounts] = React.useState<Account[]>([]);
  const [isUploading, setIsUploading] = React.useState(false);
  const [photoStatus, setPhotoStatus] = React.useState<string | null>(null);
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  React.useEffect(() => {
    if (!token || isAnalyst) return;
    let active = true;
    fetch(`${apiBaseUrl}/api/accounts`, {headers: {Authorization: `Bearer ${token}`}})
      .then(async response => {
        if (handleForbiddenResponse(response, handleForbidden)) return;
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(data?.detail || 'Nie udało się pobrać rachunków.');
        if (active) setAccounts(data?.accounts ?? []);
      })
      .catch(error => console.warn('Unable to load accounts for profile settings', error));
    return () => { active = false; };
  }, [apiBaseUrl, token, isAnalyst, handleForbidden]);

  async function changeProfileImage() {
    try {
      const options: ImageLibraryOptions = {
        mediaType: 'photo', selectionLimit: 1, assetRepresentationMode: 'compatible',
        maxWidth: 1024, maxHeight: 1024, quality: 0.8,
      };
      const result = await launchImageLibrary(options);
      if (result.didCancel) return;
      const asset = result.assets?.[0];
      if (result.errorCode || !asset?.uri || !token) {
        throw new Error(result.errorMessage ?? 'Nie wybrano poprawnego obrazu.');
      }
      if (asset.fileSize && asset.fileSize > 2 * 1024 * 1024) {
        throw new Error('Zdjęcie może mieć maksymalnie 2 MiB.');
      }
      const form = new FormData();
      form.append('file', {
        uri: asset.uri, name: asset.fileName ?? 'profile-photo.jpg', type: asset.type ?? 'image/jpeg',
      } as any);
      setIsUploading(true);
      setPhotoStatus('Wysyłam zdjęcie na serwer…');
      const response = await fetch(`${apiBaseUrl}/api/profile/photo`, {
        method: 'PUT', headers: {Authorization: `Bearer ${token}`}, body: form,
      });
      if (handleForbiddenResponse(response, handleForbidden)) return;
      console.info('Profile photo upload response', response.status);
      if (!response.ok) {
        const data = await response.json().catch(() => null);
        throw new Error(data?.detail || `Serwer odrzucił zdjęcie (HTTP ${response.status}).`);
      }
      refreshProfilePhoto();
      setPhotoStatus('Zdjęcie profilowe zostało zapisane.');
    } catch (error) {
      setPhotoStatus(error instanceof Error ? error.message : 'Wystąpił błąd podczas zmiany zdjęcia.');
    } finally {
      setIsUploading(false);
    }
  }

  const title: Record<ProfilePage, string> = {
    main: 'Profil', currency: 'Waluta i lokalizacja', appearance: 'Wygląd',
    account: 'Dane profilu', help: 'Pomoc i informacje',
  };
  const selectManualCurrency = (currency: string) => {
    if (locationCurrencyEnabled) setLocationCurrencyEnabled(false);
    setPreferredCurrency(currency);
  };
  const signOut = () => Alert.alert('Wylogować się?', 'Twoja sesja zostanie zakończona.', [
    {text: 'Anuluj', style: 'cancel'}, {text: 'Wyloguj się', style: 'destructive', onPress: onLogout},
  ]);

  return (
    <View style={styles.screen}>
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.headerRow}>
        <View style={styles.backPlaceholder} />
        <Text style={styles.headerTitle}>{title[page]}</Text>
        <BrandLogo size={38} />
      </View>
      {page === 'main' ? (
        <>
          {!isAnalyst ? <View style={styles.userCard}>
            <BrandLogo size={64} showProfilePhoto />
            <View style={styles.userCardText}>
              <Text style={styles.userTitle}>{username}</Text>
              <Text style={styles.description}>Twoje konto i preferencje</Text>
            </View>
          </View> : null}

          {!isAnalyst ? <Text style={styles.groupTitle}>Preferencje</Text> : null}
          {!isAnalyst ? <MenuRow icon={MapPin} title="Waluta i lokalizacja" subtitle={preferredCurrency ?? 'Wybierz preferencje'} onPress={() => setPage('currency')} /> : null}
          <MenuRow icon={Palette} title="Wygląd aplikacji" subtitle={THEME_LABELS[colorScheme]} onPress={() => setPage('appearance')} />

          {!isAnalyst ? <Text style={styles.groupTitle}>Konto i bezpieczeństwo</Text> : null}
          {!isAnalyst ? <MenuRow icon={Shield} title="Dane profilu" subtitle="Zdjęcie profilowe" onPress={() => setPage('account')} /> : null}

          <Text style={styles.groupTitle}>Inne</Text>
          <MenuRow icon={CircleHelp} title="Pomoc i informacje" onPress={() => setPage('help')} />
          <Pressable accessibilityRole="button" accessibilityLabel="Wyloguj się z aplikacji" onPress={signOut} style={({pressed}) => [styles.logoutRow, pressed && styles.pressed]}>
            <LogOut size={20} color="#F87171" />
            <Text style={styles.logoutText}>Wyloguj się z aplikacji</Text>
          </Pressable>
        </>
      ) : null}

      {page === 'currency' ? (
        <View style={styles.pageContent}>
          <Text style={styles.groupTitle}>Preferowana waluta</Text>
          <Text style={styles.description}>Używana jako domyślny wybór na pulpicie i przy operacjach.</Text>
          {accounts.length ? accounts.map(account => (
            <Pressable key={account.id} accessibilityRole="button" accessibilityState={{selected: preferredCurrency === account.currency_code && !locationCurrencyEnabled}}
              onPress={() => selectManualCurrency(account.currency_code)} style={[styles.option, preferredCurrency === account.currency_code && !locationCurrencyEnabled && styles.optionSelected]}>
              <Text style={styles.optionTitle}>{account.currency_code}</Text>
              <Text style={styles.optionHint}>{preferredCurrency === account.currency_code && !locationCurrencyEnabled ? 'Wybrana' : 'Ustaw jako domyślną'}</Text>
            </Pressable>
          )) : <Text style={styles.description}>Nie udało się pobrać rachunków do wyboru.</Text>}

          <Text style={styles.groupTitle}>Automatyczna waluta z lokalizacji</Text>
          <Text style={styles.description}>Aplikacja sprawdzi kraj urządzenia i dobierze walutę. Nie zapisuje współrzędnych.</Text>
          <Pressable accessibilityRole="switch" accessibilityState={{checked: locationCurrencyEnabled}}
            onPress={() => setLocationCurrencyEnabled(!locationCurrencyEnabled)} style={[styles.option, locationCurrencyEnabled && styles.optionSelected]}>
            <Text style={styles.optionTitle}>{locationCurrencyEnabled ? 'Włączona' : 'Wyłączona'}</Text>
            <Text style={styles.optionHint}>{locationDetectedCurrency ? `Ostatnio wykryto: ${locationDetectedCurrency}` : 'Dotknij, aby zmienić'}</Text>
          </Pressable>
          {locationPermissionStatus !== 'NOT_REQUESTED' ? <Text style={styles.statusText}>Uprawnienie: {PERMISSION_LABELS[locationPermissionStatus]}</Text> : null}
          {locationError ? <Text style={styles.locationMessage}>{locationError}</Text> : null}
          {locationPermissionStatus === 'BLOCKED' ? <AppButton title="Otwórz ustawienia systemu" onPress={openLocationSettings} secondary /> : null}
          {locationCurrencyEnabled && locationError && locationPermissionStatus !== 'BLOCKED' ? <AppButton title="Spróbuj ponownie" onPress={retryLocationCurrency} secondary /> : null}
        </View>
      ) : null}

      {page === 'appearance' ? (
        <View style={styles.pageContent}>
          <Text style={styles.description}>Wybierz jeden z dostępnych motywów aplikacji.</Text>
          {THEME_OPTIONS.map(theme => (
            <Pressable key={theme} accessibilityRole="button" accessibilityState={{selected: colorScheme === theme}}
              onPress={() => setColorScheme(theme)} style={[styles.option, colorScheme === theme && styles.optionSelected]}>
              <Text style={styles.optionTitle}>{THEME_LABELS[theme]}</Text>
              <Text style={styles.optionHint}>{colorScheme === theme ? 'Wybrany motyw' : 'Ustaw motyw'}</Text>
            </Pressable>
          ))}
        </View>
      ) : null}

      {page === 'account' ? (
        <View style={styles.pageContent}>
          <View style={styles.userCard}>
            <BrandLogo size={64} showProfilePhoto />
            <View style={styles.userCardText}>
              <Text style={styles.userTitle}>Zdjęcie profilowe</Text>
              <Text style={styles.description}>Widoczne w aplikacji przy Twoim koncie.</Text>
            </View>
          </View>
          <AppButton title={isUploading ? 'Zapisywanie zdjęcia…' : 'Zmień zdjęcie profilowe'} onPress={changeProfileImage} />
          {photoStatus ? <Text style={styles.description}>{photoStatus}</Text> : null}
        </View>
      ) : null}

      {page === 'help' ? (
        <View style={styles.pageContent}>
          <View style={styles.infoCard}>
            <Text style={styles.userTitle}>Pecunia non olet</Text>
            <Text style={styles.description}>Aplikacja demonstracyjna do obsługi kont i podstawowych operacji finansowych.</Text>
          </View>
        </View>
      ) : null}
    </ScrollView>
    {page !== 'main' ? <View style={styles.stickyFooter}><AppButton title="Wróć do profilu" onPress={() => setPage('main')} secondary /></View> : null}
    </View>
  );
}

function MenuRow({icon: Icon, title, subtitle, onPress}: {icon: React.ComponentType<{size?: number; color?: string}>; title: string; subtitle?: string; onPress: () => void}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({pressed}) => [styles.menuRow, pressed && styles.pressed]}>
      <Icon size={20} color={COLORS.yellow} />
      <View style={styles.menuText}>
        <Text style={styles.optionTitle}>{title}</Text>
        {subtitle ? <Text style={styles.optionHint}>{subtitle}</Text> : null}
      </View>
      <ChevronRight size={20} color={COLORS.muted} />
    </Pressable>
  );
}

const THEME_OPTIONS: ColorScheme[] = ['dark', 'light', 'pink', 'blue', 'blackAndWhite', 'highContrast'];
const THEME_LABELS: Record<ColorScheme, string> = {
  dark: 'Ciemny', light: 'Jasny', pink: 'Różowy', blue: 'Niebieski', blackAndWhite: 'Czarno-biały', highContrast: 'Wysoki kontrast',
};
const PERMISSION_LABELS = {GRANTED: 'przyznane', DENIED: 'odmówione', BLOCKED: 'zablokowane', UNAVAILABLE: 'niedostępne', ERROR: 'błąd techniczny', NOT_REQUESTED: 'niepytano'} as const;

const styles = createThemedStyles(() => StyleSheet.create({
  screen: {flex: 1},
  container: {flexGrow: 1, paddingHorizontal: 22, paddingTop: 18, paddingBottom: 28, gap: 10},
  headerRow: {minHeight: 48, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginBottom: 8},
  headerTitle: {color: COLORS.white, fontSize: 22, fontWeight: '800', flex: 1, textAlign: 'center'},
  backPlaceholder: {width: 38, height: 38},
  stickyFooter: {paddingHorizontal: 22, paddingTop: 10, paddingBottom: 10, backgroundColor: COLORS.background, borderTopWidth: 1, borderTopColor: COLORS.border},
  userCard: {flexDirection: 'row', alignItems: 'center', gap: 16, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 16, padding: 16, marginBottom: 8},
  userCardText: {flex: 1, gap: 5},
  userTitle: {color: COLORS.white, fontSize: 18, fontWeight: '800'},
  groupTitle: {color: COLORS.muted, fontSize: 14, fontWeight: '700', marginTop: 18, marginBottom: 2},
  menuRow: {minHeight: 68, flexDirection: 'row', alignItems: 'center', gap: 14, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 14, paddingHorizontal: 16, paddingVertical: 12},
  menuText: {flex: 1, gap: 4},
  option: {alignSelf: 'stretch', minHeight: 58, backgroundColor: COLORS.surface, borderColor: COLORS.border, borderRadius: 12, borderWidth: 1, padding: 14, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 12},
  optionSelected: {borderColor: COLORS.yellow},
  optionTitle: {color: COLORS.white, fontSize: 15, fontWeight: '700'},
  optionHint: {color: COLORS.muted, fontSize: 12, flexShrink: 1, textAlign: 'left'},
  description: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 14, lineHeight: 21},
  pageContent: {gap: 12},
  statusText: {color: COLORS.muted, fontSize: 13},
  locationMessage: {color: COLORS.muted, fontSize: 14, lineHeight: 20},
  infoCard: {backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 14, padding: 16, gap: 8},
  logoutRow: {minHeight: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12, paddingHorizontal: 16, marginTop: 12, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 14},
  logoutText: {color: '#F87171', fontSize: 15, fontWeight: '700'},
  pressed: {opacity: 0.78},
}));
