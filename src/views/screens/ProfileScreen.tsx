import {authenticatedFetch} from '../../auth/session';
import React from 'react';
import {Alert, BackHandler, Linking, Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';
import ChevronRight from 'lucide-react-native/icons/chevron-right';
import MapPin from 'lucide-react-native/icons/map-pin';
import Palette from 'lucide-react-native/icons/palette';
import Shield from 'lucide-react-native/icons/shield';
import CircleHelp from 'lucide-react-native/icons/circle-question-mark';
import LogOut from 'lucide-react-native/icons/log-out';
import QRCode from 'react-native-qrcode-svg';
import Clipboard from '@react-native-clipboard/clipboard';
import {launchImageLibrary, type ImageLibraryOptions} from 'react-native-image-picker';
import {API_URL} from '@env';
import {createPasskey, getPasskeys, reauthenticateWithGoogle, removePasskey, signInWithGoogle} from '../../auth/authMethods';

import {AppButton, BrandLogo, FormInput} from '../components/Ui';
import {COLORS, createThemedStyles, type ColorScheme} from '../theme';
import {handleForbiddenResponse, useAppPreferences} from '../../context/AppPreferences';
import type {Account} from '../../types/Account';
import type {UserRole} from '../../models/auth';

type ProfilePage = 'main' | 'currency' | 'appearance' | 'account' | 'help' | 'security';

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
  const [totpEnabled, setTotpEnabled] = React.useState(false);
  const [totpUri, setTotpUri] = React.useState('');
  const [totpSecret, setTotpSecret] = React.useState('');
  const [totpPassword, setTotpPassword] = React.useState('');
  const [totpCode, setTotpCode] = React.useState('');
  const [totpMessage, setTotpMessage] = React.useState('');
  const [passkeys, setPasskeys] = React.useState<Array<{id: string; label: string; created_at: number}>>([]);
  const [passkeyMessage, setPasskeyMessage] = React.useState('');
  const [recoveryCodes, setRecoveryCodes] = React.useState<string[]>([]);
  const needsRecoveryCodeCopy = recoveryCodes.length > 0;
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  React.useEffect(() => {
    if (!needsRecoveryCodeCopy) return;
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => true);
    return () => subscription.remove();
  }, [needsRecoveryCodeCopy]);

  React.useEffect(() => {
    if (!token) return;
    authenticatedFetch(`${apiBaseUrl}/api/mfa`, {headers: {Authorization: `Bearer ${token}`}})
      .then(response => response.json()).then(data => setTotpEnabled(Boolean(data?.totp_enabled)))
      .catch(() => setTotpMessage('Nie udało się pobrać statusu TOTP.'));
  }, [apiBaseUrl, token]);

  React.useEffect(() => {
    if (!token) return;
    getPasskeys(token).then(data => setPasskeys(Array.isArray(data) ? data : []))
      .catch(error => setPasskeyMessage(error instanceof Error ? error.message : 'Nie udało się pobrać passkeys.'));
  }, [token]);

  async function addPasskey() {
    if (!token) return;
    try {
      const created = await createPasskey(token);
      setPasskeys(current => [created, ...current]);
      setPasskeyMessage('Passkey została dodana.');
    } catch (error) {
      setPasskeyMessage(error instanceof Error ? error.message : 'Nie udało się dodać passkey. Zaloguj się ponownie i spróbuj ponownie.');
    }
  }

  async function connectGoogle() {
    if (!token) return;
    try {
      await signInWithGoogle(token);
      setPasskeyMessage('Konto Google zostało połączone.');
    } catch (error) {
      setPasskeyMessage(error instanceof Error ? error.message : 'Nie udało się połączyć konta Google.');
    }
  }

  async function confirmGoogleIdentity() {
    if (!token) return;
    try {
      await reauthenticateWithGoogle(token);
      setPasskeyMessage('Tożsamość Google została potwierdzona na 5 minut.');
    } catch (error) {
      setPasskeyMessage(error instanceof Error ? error.message : 'Nie udało się potwierdzić tożsamości Google.');
    }
  }

  function confirmPasskeyRemoval(id: string) {
    Alert.alert('Usunąć passkey?', 'Usunięcie jej uniemożliwi logowanie tą metodą.', [
      {text: 'Anuluj', style: 'cancel'},
      {text: 'Usuń', style: 'destructive', onPress: async () => {
        if (!token) return;
        try {
          await removePasskey(token, id);
          setPasskeys(current => current.filter(item => item.id !== id));
          setPasskeyMessage('Passkey została usunięta.');
        } catch (error) {
          setPasskeyMessage(error instanceof Error ? error.message : 'Nie udało się usunąć passkey.');
        }
      }},
    ]);
  }

  async function requestTotp(path: string, body: object) {
    const response = await authenticatedFetch(`${apiBaseUrl}/api/${path}`, {
      method: 'POST', headers: {Authorization: `Bearer ${token}`, 'Content-Type': 'application/json'},
      body: JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.detail || `Błąd serwera (${response.status}).`);
    return data;
  }

  async function beginTotpSetup() {
    try {
      const data = await requestTotp('mfa/totp/setup', {current_password: totpPassword || undefined});
      setTotpUri(data.provisioning_uri); setTotpSecret(data.secret);
      setTotpMessage('Zeskanuj kod lub wpisz sekret w aplikacji Authenticator.');
    } catch (error) { setTotpMessage(error instanceof Error ? error.message : 'Nie udało się rozpocząć konfiguracji.'); }
  }

  async function openAuthenticator() {
    try {
      await Linking.openURL(totpUri);
      setTotpMessage('Dokończ dodawanie konta w aplikacji Authenticator.');
    } catch {
      setTotpMessage('Brak aplikacji obsługującej ten link. Zeskanuj kod QR lub wpisz sekret ręcznie.');
    }
  }

  async function confirmTotp() {
    try {
      const data = await requestTotp('mfa/totp/confirm', {code: totpCode});
      setTotpEnabled(true); setTotpUri(''); setTotpSecret('');
      setRecoveryCodes(data.recovery_codes ?? []);
      setTotpCode('');
      Alert.alert(
        'TOTP włączone',
        `Skopiuj i zapisz poniższe kody przywracania. Nie zostaną one wyświetlone ponownie. Po skopiowaniu ze względów bezpieczeństwa nastąpi wylogowanie.

${(data.recovery_codes ?? []).join('\n')}`,
        [{text: 'Skopiuj kody i wyloguj', onPress: () => {
          Clipboard.setString((data.recovery_codes ?? []).join('\n'));
          onLogout();
        }}],
        {cancelable: false},
      );
    } catch (error) { setTotpMessage(error instanceof Error ? error.message : 'Nie udało się potwierdzić kodu.'); }
  }

  async function disableTotp() {
    try {
      await requestTotp('mfa/totp/disable', {current_password: totpPassword || undefined, code: totpCode});
      setTotpEnabled(false); setTotpCode('');
      Alert.alert('TOTP wyłączone', 'Ze względów bezpieczeństwa nastąpi wylogowanie.', [
        {text: 'Zaloguj się ponownie', onPress: onLogout},
      ]);
    } catch (error) { setTotpMessage(error instanceof Error ? error.message : 'Nie udało się wyłączyć TOTP.'); }
  }

  React.useEffect(() => {
    if (!token || isAnalyst) return;
    let active = true;
    authenticatedFetch(`${apiBaseUrl}/api/accounts`, {headers: {Authorization: `Bearer ${token}`}})
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
      const response = await authenticatedFetch(`${apiBaseUrl}/api/profile/photo`, {
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
    account: 'Dane profilu', help: 'Pomoc i informacje', security: 'Bezpieczeństwo',
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

          <MenuRow icon={Shield} title="Bezpieczeństwo" subtitle={`${totpEnabled ? 'TOTP włączone' : 'TOTP wyłączone'} · ${passkeys.length} passkeys`} onPress={() => setPage('security')} />
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

      {page === 'security' ? (
        <View style={styles.pageContent}>
          <Text style={styles.groupTitle}>Passkeys</Text>
          <Text style={styles.description}>Logowanie kluczem zapisanym w pęku kluczy lub menedżerze haseł urządzenia. Dodawanie i usuwanie wymaga ponownego logowania w ciągu ostatnich 5 minut.</Text>
          <AppButton title="Dodaj passkey" onPress={addPasskey} />
          {passkeys.map(item => <Pressable key={item.id} accessibilityRole="button" onPress={() => confirmPasskeyRemoval(item.id)} style={styles.option}>
            <Text style={styles.optionTitle}>{item.label}</Text><Text style={styles.optionHint}>Usuń</Text>
          </Pressable>)}
          <AppButton title="Połącz konto Google" onPress={connectGoogle} secondary />
          <AppButton title="Potwierdź tożsamość przez Google" onPress={confirmGoogleIdentity} secondary />
          {passkeyMessage ? <Text selectable style={styles.description}>{passkeyMessage}</Text> : null}
          <Text style={styles.groupTitle}>TOTP / Authenticator</Text>
          <Text style={styles.description}>{totpEnabled ? 'TOTP jest włączone dla Twojego konta.' : 'Zabezpiecz logowanie kodem z aplikacji Authenticator.'}</Text>
          <FormInput label="Obecne hasło" value={totpPassword} onChangeText={setTotpPassword} secureTextEntry />
          <Text style={styles.description}>Nie masz hasła do konta utworzonego przez Google? Zaloguj się ponownie przez Google i pozostaw to pole puste.</Text>
          {!totpEnabled && !totpUri ? <AppButton title="Rozpocznij konfigurację TOTP" onPress={beginTotpSetup} /> : null}
          {totpUri ? <>
            <QRCode value={totpUri} size={210} />
            <Pressable accessibilityRole="link" onPress={openAuthenticator} style={({pressed}) => [styles.authenticatorLink, pressed && styles.pressed]}>
              <Text style={styles.authenticatorLinkText}>Otwórz w aplikacji Authenticator</Text>
            </Pressable>
            <Text selectable style={styles.description}>Sekret do wpisania ręcznie: {totpSecret}</Text>
            <FormInput label="Kod z Authenticatora" value={totpCode} onChangeText={setTotpCode} keyboardType="number-pad" maxLength={6} />
            <AppButton title="Potwierdź i włącz TOTP" onPress={confirmTotp} />
          </> : null}
          {totpEnabled && !needsRecoveryCodeCopy ? <>
            <FormInput label="Kod TOTP lub kod odzyskiwania" value={totpCode} onChangeText={setTotpCode} autoCapitalize="characters" />
            <AppButton title="Wyłącz TOTP" onPress={disableTotp} secondary />
          </> : null}
          {recoveryCodes.length ? <>
            <Text style={styles.description}>Kody odzyskiwania możesz wykorzystać pojedynczo, jeśli nie masz dostępu do Authenticatora. Zapisz je teraz — nie będą ponownie wyświetlone.</Text>
            <View style={styles.infoCard}>
              {recoveryCodes.map(code => <Text key={code} selectable style={styles.optionTitle}>{code}</Text>)}
            </View>
            <AppButton title="Kopiuj kody odzyskiwania" onPress={() => {
              Clipboard.setString(recoveryCodes.join('\n'));
              onLogout();
            }} secondary />
            <AppButton title="Wyloguj się i zaloguj ponownie" onPress={onLogout} />
          </> : null}
          {totpMessage ? <Text selectable style={styles.description}>{totpMessage}</Text> : null}
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
    {page !== 'main' && !needsRecoveryCodeCopy ? <View style={styles.stickyFooter}><AppButton title="Wróć do profilu" onPress={() => setPage('main')} secondary /></View> : null}
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
  authenticatorLink: {alignSelf: 'center', paddingVertical: 6, paddingHorizontal: 10},
  authenticatorLinkText: {color: COLORS.yellow, fontSize: 14, fontWeight: '700', textDecorationLine: 'underline'},
  logoutRow: {minHeight: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 12, paddingHorizontal: 16, marginTop: 12, backgroundColor: COLORS.surface, borderWidth: 1, borderColor: COLORS.border, borderRadius: 14},
  logoutText: {color: '#F87171', fontSize: 15, fontWeight: '700'},
  pressed: {opacity: 0.78},
}));
