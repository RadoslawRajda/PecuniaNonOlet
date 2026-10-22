import {useState} from 'react';
import {Alert} from 'react-native';

import {
  LoginData,
  RegisterData,
  ScreenName,
  validateLogin,
  validateRegister,
} from '../models/auth';

export function useAppController() {
  const [screen, setScreen] = useState<ScreenName>('home');

  const goHome = () => setScreen('home');
  const goLogin = () => setScreen('login');
  const goRegister = () => setScreen('register');

  function submitLogin(data: LoginData) {
    const error = validateLogin(data);

    if (error) {
      Alert.alert('Błąd', error);
      return;
    }

    Alert.alert(
      'Logowanie',
      'Formularz jest poprawny. Logowanie do serwera nie jest jeszcze podłączone.',
    );
  }

  function submitRegister(data: RegisterData) {
    const error = validateRegister(data);

    if (error) {
      Alert.alert('Błąd', error);
      return;
    }

    Alert.alert(
      'Rejestracja',
      'Formularz jest poprawny. Rejestracja wymaga jeszcze backendu.',
    );
  }

  function loginWithPasskey() {
    Alert.alert(
      'Passkey',
      'Logowanie za pomocą passkey zostanie dodane po podłączeniu backendu.',
    );
  }

  return {
    screen,
    goHome,
    goLogin,
    goRegister,
    submitLogin,
    submitRegister,
    loginWithPasskey,
  };
}