import { useState, useEffect, useRef } from 'react';
import { Alert } from 'react-native';
import * as Keychain from 'react-native-keychain';
import AsyncStorage from '@react-native-async-storage/async-storage';

import { API_URL } from '@env';

import {
  LoginData,
  RegisterData,
  ScreenName,
  validateLogin,
  validateRegister,
} from '../models/auth';
import type {UserRole} from '../models/auth';

const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
const TOKEN_STORAGE_KEY = '@app_auth_token';
const ROLE_STORAGE_KEY = '@app_user_role';

function isUserRole(value: unknown): value is UserRole {
  return value === 'user' || value === 'analyst';
}

const KEYCHAIN_OPTIONS = {
  service: TOKEN_STORAGE_KEY,
  accessible: Keychain.ACCESSIBLE.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
};

export function useAppController() {
  const [screen, setScreen] = useState<ScreenName>('loading');
  const screenHistory = useRef<ScreenName[]>([]);
  const [username, setUsername] = useState<string>('test user');
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);

  function navigate(nextScreen: ScreenName) {
    if (nextScreen === screen) return;
    if (screen !== 'loading') screenHistory.current.push(screen);
    setScreen(nextScreen);
  }

  function goBack() {
    const previousScreen = screenHistory.current.pop();
    if (!previousScreen) return false;
    setScreen(previousScreen);
    return true;
  }

  function resetToHome() {
    screenHistory.current = [];
    setScreen('home');
  }

  function resetToDashboard() {
    screenHistory.current = [];
    setScreen('dashboard');
  }

  // Sprawdzanie zapisanego tokena przy starcie aplikacji
  useEffect(() => {
    async function loadStoredToken() {
      let wentToDashboard = false;

      try {
        // Pobieranie tokena z Keychain
        const credentials = await Keychain.getGenericPassword(
          KEYCHAIN_OPTIONS
        );

        const savedToken = credentials
          ? credentials.password
          : null;
        const savedRole = await AsyncStorage.getItem(ROLE_STORAGE_KEY);

        if (savedToken) {
          try {
            const response = await fetch(`${apiBaseUrl}/api/me`, {
              method: 'GET',
              headers: {
                'Authorization': `Bearer ${savedToken}`,
                'Content-Type': 'application/json',
              },
            });

            const responseData = await response.json().catch(() => null);

            if (response.ok && responseData) {
              const verifiedRole: UserRole = isUserRole(responseData.role)
                ? responseData.role
                : isUserRole(savedRole) ? savedRole : 'user';
              setRole(verifiedRole);
              void AsyncStorage.setItem(ROLE_STORAGE_KEY, verifiedRole)
                .catch(error => console.warn('Unable to save user role', error));
              setToken(savedToken);
              if (responseData.email) {
                setUsername(responseData.email);
              }
              resetToDashboard();
              wentToDashboard = true;
            } else {
              // Usuwanie nieprawidłowego tokena z Keychain
              await Keychain.resetGenericPassword(KEYCHAIN_OPTIONS);
              await AsyncStorage.removeItem(ROLE_STORAGE_KEY);
              setRole(null);
              setToken(null);
            }
          } catch {
            setRole(isUserRole(savedRole) ? savedRole : 'user');
            setToken(savedToken);
            resetToDashboard();
            wentToDashboard = true;
          }
        } else {
          setRole(null);
          await AsyncStorage.removeItem(ROLE_STORAGE_KEY);
        }
      } catch (e) {
        console.error('Błąd podczas odczytu tokena z pamięci:', e);
      }

      if(wentToDashboard === false)
      {
        resetToHome();
      }
    }

    loadStoredToken();
  }, []);

  const goHome = resetToHome;
  const goLogin = () => navigate('login');
  const goRegister = () => navigate('register');
  const goDashboard = () => navigate('dashboard');
  const goExchangeRates = () => navigate('exchangeRates');
  const goProfile = () => navigate('profile');
  const goQrScanner = () => navigate('qrScanner');
  const goQrHub = () => navigate('qrHub');
  const goQrGeneration = () => navigate('qrGeneration');
  const goTransactionHistory = () => navigate('transactionHistory');

  async function submitLogin(data: LoginData) {
    const error = validateLogin(data);

    if (error) {
      Alert.alert('Błąd', error);
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/login`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      const responseData = await response.json().catch(() => null);

      if (response.ok && responseData) {
        if (responseData.token) {
          const loginRole: UserRole = isUserRole(responseData.user?.role) ? responseData.user.role : 'user';
          setRole(loginRole);
          void AsyncStorage.setItem(ROLE_STORAGE_KEY, loginRole)
            .catch(error => console.warn('Unable to save user role', error));
          setToken(responseData.token);

          // Bezpieczne zapisanie tokena w Keychain
          await Keychain.setGenericPassword(
            'app-auth-token',
            responseData.token,
            KEYCHAIN_OPTIONS
          );
        }

        if (responseData.user && responseData.user.email) {
          setUsername(responseData.user.email);
        }

        resetToDashboard();
      } else {
        Alert.alert(
          'Błąd',
          JSON.stringify(
            responseData?.detail || {
              status: response.status,
              ok: response.ok,
            },
            null,
            2
          )
        );
      }
    } catch (e: any) {
      Alert.alert(
        'Błąd sieci',
        `${e?.message || 'Nie udało się połączyć z serwerem.'}\nAdres: ${apiBaseUrl}/api/login`,
      );
    }
  }

  async function submitRegister(data: RegisterData) {
    const error = validateRegister(data);

    if (error) {
      Alert.alert('Błąd', error);
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/register`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({email: data.email.trim(), password: data.password}),
      });

      const responseData = await response.json().catch(() => null);

      if (response.ok && responseData) {
        if (responseData.token) {
          const registeredRole: UserRole = isUserRole(responseData.user?.role) ? responseData.user.role : 'user';
          setRole(registeredRole);
          void AsyncStorage.setItem(ROLE_STORAGE_KEY, registeredRole)
            .catch(error => console.warn('Unable to save user role', error));
          setToken(responseData.token);

          // Bezpieczne zapisanie tokena w Keychain
          await Keychain.setGenericPassword(
            'app-auth-token',
            responseData.token,
            KEYCHAIN_OPTIONS
          );
        }

        if (responseData.user && responseData.user.email) {
          setUsername(responseData.user.email);
        }

        resetToDashboard();
      } else {
        Alert.alert(
          'Błąd',
          JSON.stringify(
            responseData?.detail || {
              status: response.status,
              ok: response.ok,
            },
            null,
            2
          )
        );
      }
    } catch (e: any) {
      Alert.alert(
        'Błąd sieci',
        `${e?.message || 'Nie udało się połączyć z serwerem.'}\nAdres: ${apiBaseUrl}/api/register`,
      );
    }
  }

  async function logout() {
    try {
      if (token) {
        await fetch(`${apiBaseUrl}/api/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
        });
        Alert.alert("",
          "Wylogowano",
          [
            {
              text: 'OK',
              onPress: async () => {
                  goHome();
                }
            }
          ]
        );
      }
    } catch (e) {
      console.error('Błąd podczas wylogowywania:', e);
    } finally {
      // Usuwanie tokena z Keychain
      await Keychain.resetGenericPassword(KEYCHAIN_OPTIONS);

      setToken(null);
      setRole(null);
      await AsyncStorage.removeItem(ROLE_STORAGE_KEY);
      setUsername('test user');
    }
  }

  async function getinfo() {
    if (!token) {
      Alert.alert('Błąd', 'Brak aktywnego tokenu. Zaloguj się ponownie.');
      goHome();
      return;
    }

    try {
      const response = await fetch(`${apiBaseUrl}/api/me`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${token}`,
          'Content-Type': 'application/json',
        },
      });

      const responseData = await response.json().catch(() => null);

      if (response.ok && responseData) {
        if (responseData.email) {
          setUsername(responseData.email);
        }
        Alert.alert('Informacje o użytkowniku', JSON.stringify(responseData, null, 2));
      } else {
        Alert.alert('Błąd', 'Nie udało się pobrać danych użytkownika.');
      }
    } catch (e: any) {
      Alert.alert(
        'Błąd sieci',
        `${e?.message || 'Nie udało się połączyć z serwerem.'}\nAdres: ${apiBaseUrl}/api/me`,
      );
    }
  }

  function loginWithPasskey() {
    Alert.alert(
      'Passkey',
      'Logowanie za pomocą passkey zostanie dodane po podłączeniu backendu.',
    );
  }

  return {
    screen,
    goBack,
    username,
    token,
    role,
    goHome,
    goLogin,
    goRegister,
    goDashboard,
    goExchangeRates,
    goProfile,
    goQrScanner,
    goQrHub,
    goQrGeneration,
    goTransactionHistory,
    submitLogin,
    submitRegister,
    loginWithPasskey,
    logout,
    getinfo,
  };
}
