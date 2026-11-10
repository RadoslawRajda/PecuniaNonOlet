import { useState, useEffect } from 'react';
import { Alert } from 'react-native';
import * as Keychain from 'react-native-keychain';

import { API_URL } from '@env';

import {
  LoginData,
  RegisterData,
  ScreenName,
  validateLogin,
  validateRegister,
} from '../models/auth';

const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
const TOKEN_STORAGE_KEY = '@app_auth_token';

const KEYCHAIN_OPTIONS = {
  service: TOKEN_STORAGE_KEY,
};

export function useAppController() {
  const [screen, setScreen] = useState<ScreenName>('loading');
  const [username, setUsername] = useState<string>('test user');
  const [token, setToken] = useState<string | null>(null);

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

        if (savedToken) {
          setToken(savedToken);

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
              if (responseData.email) {
                setUsername(responseData.email);
              }
              setScreen('dashboard'); 
              wentToDashboard = true;
            } else {
              // Usuwanie nieprawidłowego tokena z Keychain
              await Keychain.resetGenericPassword(KEYCHAIN_OPTIONS);
              setToken(null);
            }
          } catch {
            setToken(savedToken);
            setScreen('dashboard');
            wentToDashboard = true;
          }
        }
      } catch (e) {
        console.error('Błąd podczas odczytu tokena z pamięci:', e);
      }

      if(wentToDashboard === false)
      {
        setScreen('home'); 
      }
    }

    loadStoredToken();
  }, []);

  const goHome = () => setScreen('home');
  const goLogin = () => setScreen('login');
  const goRegister = () => setScreen('register');
  const goDashboard = () => setScreen('dashboard');
  const goExchangeRates = () => setScreen('exchangeRates');
  const goProfile = () => setScreen('profile');
  const goQrScanner = () => setScreen('qrScanner');
  const goTransactionHistory = () => setScreen('transactionHistory');

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

        goDashboard();
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

        goDashboard();
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
      setUsername('test user');
    }
  }

  async function getinfo() {
    if (!token) {
      Alert.alert('Błąd', 'Brak aktywnego tokenu. Zaloguj się ponownie.');
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
    username,
    token,
    goHome,
    goLogin,
    goRegister,
    goDashboard,
    goExchangeRates,
    goProfile,
    goQrScanner,
    goTransactionHistory,
    submitLogin,
    submitRegister,
    loginWithPasskey,
    logout,
    getinfo,
  };
}