import React, {createContext, useCallback, useContext, useEffect, useMemo, useRef, useState} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {Platform} from 'react-native';
import Geolocation from 'react-native-geolocation-service';
import {check, PERMISSIONS, request, RESULTS} from 'react-native-permissions';
import {API_URL} from '@env';
import type {PropsWithChildren} from 'react';
import {setColorScheme, type ColorScheme} from '../views/theme';
import { Alert } from 'react-native';
import type {UserRole} from '../models/auth';

const THEME_KEY = '@app_theme';
const CURRENCY_KEY = '@app_preferred_currency';
const DEFAULT_CURRENCY = 'PLN';
const LOCATION_CURRENCY_KEY = '@app_location_currency_enabled';
const LOCATION_CURRENCY_RESULT_KEY = '@app_location_currency_result';
const COUNTRY_CURRENCIES: Record<string, string> = {
  PL: 'PLN', CZ: 'CZK', GB: 'GBP', US: 'USD',
  AT: 'EUR', BE: 'EUR', CY: 'EUR', DE: 'EUR', EE: 'EUR', ES: 'EUR', FI: 'EUR',
  FR: 'EUR', GR: 'EUR', HR: 'EUR', IE: 'EUR', IT: 'EUR', LT: 'EUR', LU: 'EUR',
  LV: 'EUR', MT: 'EUR', NL: 'EUR', PT: 'EUR', SI: 'EUR', SK: 'EUR',
};

type Preferences = {
  token: string | null;
  colorScheme: ColorScheme;
  preferencesLoaded: boolean;
  preferredCurrency: string | null;
  locationCurrencyEnabled: boolean;
  locationDetectedCurrency: string | null;
  profilePhotoRevision: number;
  profilePhotoDataUri: string | null;
  profilePhotoResolved: boolean;
  setColorScheme: (scheme: ColorScheme) => void;
  setPreferredCurrency: (currency: string) => void;
  setLocationCurrencyEnabled: (enabled: boolean) => void;
  refreshProfilePhoto: () => void;
};

const PreferencesContext = createContext<Preferences | null>(null);

export function AppPreferencesProvider({token, role, children}: PropsWithChildren<{token: string | null; role: UserRole | null}>) {
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>('dark');
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [preferredCurrency, setPreferredCurrencyState] = useState<string | null>(null);
  const [manualPreferredCurrency, setManualPreferredCurrency] = useState<string | null>(null);
  const [locationCurrencyEnabled, setLocationCurrencyEnabledState] = useState(false);
  const [locationDetectedCurrency, setLocationDetectedCurrency] = useState<string | null>(null);
  const [profilePhotoRevision, setProfilePhotoRevision] = useState(0);
  const [profilePhoto, setProfilePhoto] = useState<{token: string; dataUri: string} | null>(null);
  const [photoResolvedToken, setPhotoResolvedToken] = useState<string | null>(null);
  const previousToken = useRef(token);
  const locationCheckStarted = useRef(false);

  useEffect(() => {
    if (previousToken.current !== token) {
      previousToken.current = token;
      setProfilePhotoRevision(current => current + 1);
      if (token) locationCheckStarted.current = false;
    }
  }, [token]);

  useEffect(() => {
    if (!token || role !== 'user') {
      setProfilePhoto(null);
      setPhotoResolvedToken(role === 'analyst' ? token : null);
      return;
    }

    let active = true;
    setPhotoResolvedToken(null);
    fetch(profilePhotoUrl(profilePhotoRevision), {
      headers: {Authorization: `Bearer ${token}`},
    })
      .then(async response => {
        if (response.status === 404) return null;
        if (!response.ok) throw new Error(`Photo request failed (${response.status})`);
        const blob = await response.blob();
        return await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Unable to read profile photo'));
          reader.onerror = () => reject(reader.error ?? new Error('Unable to read profile photo'));
          reader.readAsDataURL(blob);
        });
      })
      .then(uri => {
        if (!active) return;
        if (uri) setProfilePhoto({token, dataUri: uri});
        setPhotoResolvedToken(token);
      })
      .catch(error => {
        if (!active) return;
        console.error('Profile photo fetch failed', error);
        setPhotoResolvedToken(token);
      });

    return () => { active = false; };
  }, [token, role, profilePhotoRevision]);

  useEffect(() => {
    let active = true;
    Promise.all([
      AsyncStorage.getItem(THEME_KEY),
      AsyncStorage.getItem(CURRENCY_KEY),
      AsyncStorage.getItem(LOCATION_CURRENCY_KEY),
      AsyncStorage.getItem(LOCATION_CURRENCY_RESULT_KEY),
    ])
      .then(([savedTheme, savedCurrency, savedLocationCurrency, savedLocationResult]) => {
        if (!active) return;
        const validThemes: ColorScheme[] = ['dark', 'light', 'pink', 'blue', 'blackAndWhite', 'highContrast'];
        const nextTheme: ColorScheme = validThemes.includes(savedTheme as ColorScheme) ? savedTheme as ColorScheme : 'dark';
        const initialCurrency = savedCurrency || DEFAULT_CURRENCY;
        const locationEnabled = savedLocationCurrency === 'true';
        const validLocationResult = savedLocationResult && Object.values(COUNTRY_CURRENCIES).includes(savedLocationResult)
          ? savedLocationResult
          : null;
        setColorScheme(nextTheme);
        setColorSchemeState(nextTheme);
        setPreferredCurrencyState(initialCurrency);
        setManualPreferredCurrency(initialCurrency);
        if (!savedCurrency) {
          AsyncStorage.setItem(CURRENCY_KEY, DEFAULT_CURRENCY)
            .catch(error => console.warn('Unable to save default preferred currency', error));
        }
        setLocationCurrencyEnabledState(locationEnabled);
        setLocationDetectedCurrency(validLocationResult);
        if (locationEnabled && validLocationResult) {
          setPreferredCurrencyState(validLocationResult);
          locationCheckStarted.current = true;
        }
      })
      .catch(error => console.warn('Unable to load preferences', error))
      .finally(() => { if (active) setPreferencesLoaded(true); });
    return () => { active = false; };
  }, []);

  const updateColorScheme = useCallback((scheme: ColorScheme) => {
    setColorScheme(scheme);
    setColorSchemeState(scheme);
    AsyncStorage.setItem(THEME_KEY, scheme).catch(error => console.warn('Unable to save theme', error));
  }, []);

  const updatePreferredCurrency = useCallback((currency: string) => {
    setPreferredCurrencyState(currency);
    setManualPreferredCurrency(currency);
    AsyncStorage.setItem(CURRENCY_KEY, currency).catch(error => console.warn('Unable to save preferred currency', error));
  }, []);

  const applyLocationCurrency = useCallback((currency: string) => {
    setLocationDetectedCurrency(currency);
    setPreferredCurrencyState(currency);
    AsyncStorage.setItem(LOCATION_CURRENCY_RESULT_KEY, currency).catch(error => console.warn('Unable to save location currency result', error));
  }, []);

  const updateLocationCurrencyEnabled = useCallback((enabled: boolean) => {
    setLocationCurrencyEnabledState(enabled);
    AsyncStorage.setItem(LOCATION_CURRENCY_KEY, String(enabled)).catch(error => console.warn('Unable to save location currency preference', error));
    if (!enabled) {
      locationCheckStarted.current = false;
      setLocationDetectedCurrency(null);
      setPreferredCurrencyState(manualPreferredCurrency);
      AsyncStorage.removeItem(LOCATION_CURRENCY_RESULT_KEY).catch(error => console.warn('Unable to clear location currency result', error));
    }
  }, [manualPreferredCurrency]);

  useEffect(() => {
    if (!preferencesLoaded || !token || !locationCurrencyEnabled || locationCheckStarted.current) return;
    locationCheckStarted.current = true;
    let active = true;
    const permission = Platform.OS === 'ios' ? PERMISSIONS.IOS.LOCATION_WHEN_IN_USE : PERMISSIONS.ANDROID.ACCESS_COARSE_LOCATION;
    const resolveCurrency = async () => {
      try {
        const status = await check(permission);
        const granted = status === RESULTS.GRANTED || (await request(permission)) === RESULTS.GRANTED;
        if (!granted) {
          if (!active) return;
          locationCheckStarted.current = false;
          setLocationCurrencyEnabledState(false);
          setLocationDetectedCurrency(null);
          setPreferredCurrencyState(manualPreferredCurrency);
          AsyncStorage.setItem(LOCATION_CURRENCY_KEY, 'false')
            .catch(error => console.warn('Unable to disable location currency preference', error));
          AsyncStorage.removeItem(LOCATION_CURRENCY_RESULT_KEY)
            .catch(error => console.warn('Unable to clear location currency result', error));
          Alert.alert('Błąd', 'Odmowa dostępu do lokalizacji. Proszę wybrać preferowaną walutę ręcznie.');
          return;
        }
        const position = await new Promise<{coords: {latitude: number; longitude: number}}>((resolve, reject) => {
          Geolocation.getCurrentPosition(resolve, reject, {enableHighAccuracy: false, timeout: 15000, maximumAge: 60000});
        });
        const {latitude, longitude} = position.coords;
        const url = `https://api.bigdatacloud.net/data/reverse-geocode-client?latitude=${latitude}&longitude=${longitude}&localityLanguage=pl`;
        const response = await fetch(url);
        if (!response.ok) return;
        const data = await response.json();
        const countryCode = String(data?.countryCode ?? '').toUpperCase();
        const currency = COUNTRY_CURRENCIES[countryCode];
        if (active && currency) applyLocationCurrency(currency);
      } catch (error) {
        console.warn('Unable to determine location-based currency', error);
      }
    };
    void resolveCurrency();
    return () => { active = false; };
  }, [preferencesLoaded, token, locationCurrencyEnabled, manualPreferredCurrency, applyLocationCurrency]);

  const refreshProfilePhoto = useCallback(() => setProfilePhotoRevision(current => current + 1), []);
  const value = useMemo(() => ({
    token,
    colorScheme,
    preferencesLoaded,
    preferredCurrency,
    locationCurrencyEnabled,
    locationDetectedCurrency,
    profilePhotoRevision,
    profilePhotoDataUri: token && role === 'user' && profilePhoto?.token === token ? profilePhoto.dataUri : null,
    profilePhotoResolved: !token || role === 'analyst' || photoResolvedToken === token,
    setColorScheme: updateColorScheme,
    setPreferredCurrency: updatePreferredCurrency,
    setLocationCurrencyEnabled: updateLocationCurrencyEnabled,
    refreshProfilePhoto,
  }), [token, role, colorScheme, preferencesLoaded, preferredCurrency, locationCurrencyEnabled, locationDetectedCurrency, profilePhotoRevision, profilePhoto, photoResolvedToken, updateColorScheme, updatePreferredCurrency, updateLocationCurrencyEnabled, refreshProfilePhoto]);

  return <PreferencesContext.Provider value={value}>{children}</PreferencesContext.Provider>;
}

export function useAppPreferences() {
  const preferences = useContext(PreferencesContext);
  if (!preferences) {
    throw new Error('useAppPreferences must be used within AppPreferencesProvider');
  }
  return preferences;
}

export function profilePhotoUrl(revision: number) {
  const base = (API_URL ?? '').trim().replace(/\/+$/, '');
  return `${base}/api/profile/photo?revision=${revision}`;
}
