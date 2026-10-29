import {useState} from 'react';
import {Alert} from 'react-native';

import { API_URL } from '@env';

import {
  LoginData,
  RegisterData,
  ScreenName,
  validateLogin,
  validateRegister,
} from '../models/auth';

const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

export function useAppController() {
  const [screen, setScreen] = useState<ScreenName>('home');
  const [username, setUsername] = useState<String>('test user');

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
      
      Alert.alert(
        'Odpowiedź serwera (Logowanie)',
        JSON.stringify(responseData || { status: response.status, ok: response.ok }, null, 2),
        //SetUsername(responseData.username)
        [
          {
            text: 'OK',
            onPress: () =>{
              if (response.ok) {
                goDashboard();
              }
            }
          }
        ]
      );

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

      Alert.alert(
        'Odpowiedź serwera (Rejestracja)',
        JSON.stringify(responseData || { status: response.status, ok: response.ok }, null, 2)
      );
    } catch (e: any) {
      Alert.alert(
        'Błąd sieci',
        `${e?.message || 'Nie udało się połączyć z serwerem.'}\nAdres: ${apiBaseUrl}/api/register`,
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
    goHome,
    goLogin,
    goRegister,
    goDashboard,
    submitLogin,
    submitRegister,
    loginWithPasskey,
  };
}
