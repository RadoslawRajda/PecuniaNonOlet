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
      const response = await fetch(API_URL + "/api/login", {
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
      Alert.alert('Błąd sieci', 
        e?.message + " \nAddress: " + API_URL + "\n" + JSON.stringify(data) || 'Nie udało się połączyć z serwerem.' + " \nAddress: " + API_URL + "\n" + JSON.stringify(data),
        [
          {
            text: 'OK',
            onPress: () =>{
                goDashboard();
              }
          }
        ]);
    }
  }

  async function submitRegister(data: RegisterData) {
    const error = validateRegister(data);

    if (error) {
      Alert.alert('Błąd', error);
      return;
    }

    try {
      const response = await fetch(API_URL + "/api/register", {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify(data),
      });

      const responseData = await response.json().catch(() => null);

      Alert.alert(
        'Odpowiedź serwera (Rejestracja)',
        JSON.stringify(responseData || { status: response.status, ok: response.ok }, null, 2)
      );
    } catch (e: any) {
      Alert.alert('Błąd sieci', e?.message || 'Nie udało się połączyć z serwerem.');
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