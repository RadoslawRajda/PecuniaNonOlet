import {useState, useEffect} from 'react';
import {Alert} from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';

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

export function useAppController() {
  const [screen, setScreen] = useState<ScreenName>('loading');
  const [username, setUsername] = useState<string>('test user');
  const [token, setToken] = useState<string | null>(null);

  // Sprawdzanie zapisanego tokena przy starcie aplikacji
  useEffect(() => {
    async function loadStoredToken() {
      let wentToDashboard = false;
      try {
        const savedToken = await AsyncStorage.getItem(TOKEN_STORAGE_KEY);
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
              await AsyncStorage.removeItem(TOKEN_STORAGE_KEY);
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
      
      // Alert.alert(
      //   'Odpowiedź serwera (Logowanie)',
      //   JSON.stringify(responseData || { status: response.status, ok: response.ok }, null, 2),
      //   [
      //     {
      //       text: 'OK',
      //       onPress: async () => {
      //         if (response.ok && responseData) {
      //           if (responseData.token) {
      //             setToken(responseData.token);
      //             await AsyncStorage.setItem(TOKEN_STORAGE_KEY, responseData.token);
      //           }
      //           if (responseData.user && responseData.user.email) {
      //             setUsername(responseData.user.email);
      //           }
      //           goDashboard();
      //         }
      //       }
      //     }
      //   ]
      // );
      if (response.ok && responseData) {
        if (responseData.token) {
          setToken(responseData.token);
          await AsyncStorage.setItem(TOKEN_STORAGE_KEY, responseData.token);
        }
        if (responseData.user && responseData.user.email) {
          setUsername(responseData.user.email);
        }
        goDashboard();
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

      // Alert.alert(
      //   'Odpowiedź serwera (Rejestracja)',
      //   JSON.stringify(responseData || { status: response.status, ok: response.ok }, null, 2),
      //   [
      //     {
      //       text: 'OK',
      //       onPress: async () => {
      //         if (response.ok && responseData) {
      //           if (responseData.token) {
      //             setToken(responseData.token);
      //             await AsyncStorage.setItem(TOKEN_STORAGE_KEY, responseData.token);
      //           }
      //           if (responseData.user && responseData.user.email) {
      //             setUsername(responseData.user.email);
      //           }
      //           goDashboard();
      //         }
      //       }
      //     }
      //   ]
      // );
      if (response.ok && responseData) {
          if (responseData.token) {
            setToken(responseData.token);
            await AsyncStorage.setItem(TOKEN_STORAGE_KEY, responseData.token);
          }
          if (responseData.user && responseData.user.email) {
            setUsername(responseData.user.email);
          }
          goDashboard();
      };
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
      await AsyncStorage.removeItem(TOKEN_STORAGE_KEY);
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
    submitLogin,
    submitRegister,
    loginWithPasskey,
    logout,
    getinfo,
  };
}