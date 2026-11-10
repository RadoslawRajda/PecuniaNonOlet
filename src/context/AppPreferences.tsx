import React, {createContext, useCallback, useContext, useEffect, useMemo, useRef, useState} from 'react';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {API_URL} from '@env';
import type {PropsWithChildren} from 'react';
import {setColorScheme, type ColorScheme} from '../views/theme';

const THEME_KEY = '@app_theme';
const CURRENCY_KEY = '@app_preferred_currency';

type Preferences = {
  token: string | null;
  colorScheme: ColorScheme;
  preferencesLoaded: boolean;
  preferredCurrency: string | null;
  profilePhotoRevision: number;
  profilePhotoDataUri: string | null;
  profilePhotoResolved: boolean;
  setColorScheme: (scheme: ColorScheme) => void;
  setPreferredCurrency: (currency: string) => void;
  refreshProfilePhoto: () => void;
};

const PreferencesContext = createContext<Preferences | null>(null);

export function AppPreferencesProvider({token, children}: PropsWithChildren<{token: string | null}>) {
  const [colorScheme, setColorSchemeState] = useState<ColorScheme>('dark');
  const [preferencesLoaded, setPreferencesLoaded] = useState(false);
  const [preferredCurrency, setPreferredCurrencyState] = useState<string | null>(null);
  const [profilePhotoRevision, setProfilePhotoRevision] = useState(0);
  const [profilePhoto, setProfilePhoto] = useState<{token: string; dataUri: string} | null>(null);
  const [photoResolvedToken, setPhotoResolvedToken] = useState<string | null>(null);
  const previousToken = useRef(token);

  useEffect(() => {
    if (previousToken.current !== token) {
      previousToken.current = token;
      setProfilePhotoRevision(current => current + 1);
    }
  }, [token]);

  useEffect(() => {
    if (!token) {
      setProfilePhoto(null);
      setPhotoResolvedToken(null);
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
  }, [token, profilePhotoRevision]);

  useEffect(() => {
    let active = true;
    Promise.all([AsyncStorage.getItem(THEME_KEY), AsyncStorage.getItem(CURRENCY_KEY)])
      .then(([savedTheme, savedCurrency]) => {
        if (!active) return;
        const validThemes: ColorScheme[] = ['dark', 'light', 'pink', 'blue', 'blackAndWhite', 'highContrast'];
        const nextTheme: ColorScheme = validThemes.includes(savedTheme as ColorScheme) ? savedTheme as ColorScheme : 'dark';
        setColorScheme(nextTheme);
        setColorSchemeState(nextTheme);
        setPreferredCurrencyState(savedCurrency);
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
    AsyncStorage.setItem(CURRENCY_KEY, currency).catch(error => console.warn('Unable to save preferred currency', error));
  }, []);

  const refreshProfilePhoto = useCallback(() => setProfilePhotoRevision(current => current + 1), []);
  const value = useMemo(() => ({
    token,
    colorScheme,
    preferencesLoaded,
    preferredCurrency,
    profilePhotoRevision,
    profilePhotoDataUri: token && profilePhoto?.token === token ? profilePhoto.dataUri : null,
    profilePhotoResolved: !token || photoResolvedToken === token,
    setColorScheme: updateColorScheme,
    setPreferredCurrency: updatePreferredCurrency,
    refreshProfilePhoto,
  }), [token, colorScheme, preferencesLoaded, preferredCurrency, profilePhotoRevision, profilePhoto, photoResolvedToken, updateColorScheme, updatePreferredCurrency, refreshProfilePhoto]);

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
