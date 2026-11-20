import { useState, useEffect, useRef, useCallback } from 'react';
import { Alert } from 'react-native';
import AsyncStorage from '@react-native-async-storage/async-storage';
import {signInWithGoogle, signInWithPasskey} from '../auth/authMethods';
import {authenticatedFetch, clearSessionTokens, loadSessionTokens, logoutRemoteSession, saveSessionTokens, subscribeAccessToken} from '../auth/session';

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
const ROLE_STORAGE_KEY = '@app_user_role';

function isUserRole(value: unknown): value is UserRole {
  return value === 'user' || value === 'analyst';
}

export function useAppController() {
  const [storedScreen, setScreen] = useState<ScreenName>('loading');
  const screenHistory = useRef<ScreenName[]>([]);
  const [username, setUsername] = useState<string>('test user');
  const [token, setToken] = useState<string | null>(null);
  const [role, setRole] = useState<UserRole | null>(null);
  const [mfaChallenge, setMfaChallenge] = useState<string | null>(null);
  const tokenRef = useRef(token);
  const roleRef = useRef(role);
  const forbiddenAlertPending = useRef(false);
  tokenRef.current = token;
  roleRef.current = role;
  const [pendingTransactionId, setPendingTransactionId] = useState<string | null>(null);

  async function finishFederatedLogin(responseData: any) {
    if (responseData?.mfa_required && typeof responseData.challenge_token === 'string') {
      setMfaChallenge(responseData.challenge_token);
      return;
    }
    if (!responseData?.access_token || !responseData?.refresh_token || !responseData?.user) throw new Error('Serwer nie zwrócił poprawnej sesji.');
    const loginRole: UserRole = isUserRole(responseData.user.role) ? responseData.user.role : 'user';
    setRole(loginRole);
    setToken(responseData.access_token);
    setUsername(responseData.user.email ?? '');
    setMfaChallenge(null);
    await AsyncStorage.setItem(ROLE_STORAGE_KEY, loginRole);
    await saveSessionTokens(responseData);
    if (loginRole === 'analyst') resetToAnalytics(); else resetToDashboard();
  }

  const roleHomeScreen: ScreenName = role === 'analyst' ? 'analytics' : 'dashboard';
  const allowedScreens: readonly ScreenName[] = role === 'analyst'
    ? ['home', 'login', 'register', 'analytics', 'analyticsUsers', 'analyticsTransactions', 'analyticsAuditEvents', 'profile']
    : ['home', 'login', 'register', 'dashboard', 'transactionHistory', 'exchangeRates', 'qrScanner', 'qrHub', 'profile', 'qrGeneration'];
  const screen = token && role && storedScreen !== 'loading' && !allowedScreens.includes(storedScreen)
    ? roleHomeScreen
    : storedScreen;

  useEffect(() => {
    if (screen !== storedScreen) {
      screenHistory.current = [];
      Alert.alert(
        'Brak dostępu',
        `${role === 'analyst' ? 'Analityk' : 'Użytkownik'} nie ma uprawnień do wyświetlenia tej strony.`,
      );
      setScreen(screen);
    }
  }, [screen, storedScreen, role]);

  function navigate(nextScreen: ScreenName) {
    if (nextScreen === screen) return;
    if (screen !== 'loading') screenHistory.current.push(screen);
    setScreen(nextScreen);
  }

  const goBack = useCallback(() => {
    const previousScreen = screenHistory.current.pop();
    if (!previousScreen) return false;
    setScreen(previousScreen);
    return true;
  }, []);

  const resetToHome = useCallback(() => {
    screenHistory.current = [];
    setScreen('home');
  }, []);

  useEffect(() => subscribeAccessToken(nextToken => {
    setToken(nextToken);
    if (nextToken === null) {
      setRole(null);
      void AsyncStorage.removeItem(ROLE_STORAGE_KEY);
      resetToHome();
    }
  }), [resetToHome]);

  function resetToDashboard() {
    screenHistory.current = [];
    setScreen('dashboard');
  }

  function resetToAnalytics() {
    screenHistory.current = [];
    setScreen('analytics');
  }

  function resetToAnalyticsUsers() {
    screenHistory.current = [];
    setScreen('analyticsUsers');
  }

  function resetToAnalyticsTransactions() {
    screenHistory.current = [];
    setScreen('analyticsTransactions');
  }

  function resetToAnalyticsAuditEvents() {
    screenHistory.current = [];
    setScreen('analyticsAuditEvents');
  }

  const handleForbidden = useCallback(() => {
    if (forbiddenAlertPending.current) return;
    forbiddenAlertPending.current = true;
    void (async () => {
      let actualRole = roleRef.current;
      const activeToken = tokenRef.current;
      if (activeToken) {
        try {
          const response = await authenticatedFetch(`${apiBaseUrl}/api/me`, {accessToken: activeToken});
          const data = await response.json().catch(() => null);
          if (response.ok && isUserRole(data?.role)) actualRole = data.role;
          else if (response.status === 401) actualRole = null;
        } catch (error) {
          console.warn('Unable to verify role after access denial', error);
        }
      }
      if (isUserRole(actualRole)) {
        setRole(actualRole);
        void AsyncStorage.setItem(ROLE_STORAGE_KEY, actualRole)
          .catch(error => console.warn('Unable to save verified user role', error));
      }
      Alert.alert('Brak dostępu', 'Nie masz uprawnień do wyświetlenia tej strony.', [{
        text: 'OK',
        onPress: () => {
          forbiddenAlertPending.current = false;
          if (!activeToken || !isUserRole(actualRole)) {
            setToken(null);
            setRole(null);
            void clearSessionTokens();
            void AsyncStorage.removeItem(ROLE_STORAGE_KEY);
            resetToHome();
          } else {
            screenHistory.current = [];
            setScreen(actualRole === 'analyst' ? 'analytics' : 'dashboard');
          }
        },
      }]);
    })();
  }, [resetToHome]);

  // Sprawdzanie zapisanego tokena przy starcie aplikacji
  useEffect(() => {
    async function loadStoredToken() {
      let wentToDashboard = false;

      try {
        // Pobieranie tokena z Keychain
        const savedSession = await loadSessionTokens();
        const savedToken = savedSession?.access_token ?? null;
        const savedRole = await AsyncStorage.getItem(ROLE_STORAGE_KEY);

        if (savedToken) {
          try {
            const response = await authenticatedFetch(`${apiBaseUrl}/api/me`, {
              method: 'GET',
              headers: {'Content-Type': 'application/json'},
              accessToken: savedToken,
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
              if (verifiedRole === 'analyst') resetToAnalytics();
              else resetToDashboard();
              wentToDashboard = true;
            } else {
              // Usuwanie nieprawidłowego tokena z Keychain
              await clearSessionTokens();
              await AsyncStorage.removeItem(ROLE_STORAGE_KEY);
              setRole(null);
              setToken(null);
            }
          } catch {
            const cachedRole: UserRole = isUserRole(savedRole) ? savedRole : 'user';
            setRole(cachedRole);
            setToken(savedToken);
            if (cachedRole === 'analyst') resetToAnalytics();
            else resetToDashboard();
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
  }, [resetToHome]);

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
  const openTransactionOnDashboard = (transactionId?: string) => {
    setPendingTransactionId(transactionId ?? null);
    resetToDashboard();
  };

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
        if (responseData.mfa_required && typeof responseData.challenge_token === 'string') {
          setMfaChallenge(responseData.challenge_token);
          return;
        }
        if (responseData.access_token && responseData.refresh_token) {
          const loginRole: UserRole = isUserRole(responseData.user?.role) ? responseData.user.role : 'user';
          setRole(loginRole);
          void AsyncStorage.setItem(ROLE_STORAGE_KEY, loginRole)
            .catch(error => console.warn('Unable to save user role', error));
          setToken(responseData.access_token);
          setMfaChallenge(null);

          // Bezpieczne zapisanie tokena w Keychain
          await saveSessionTokens(responseData);
        }

        if (responseData.user && responseData.user.email) {
          setUsername(responseData.user.email);
        }

        // The selected home page is based on the role returned by login.
        if (responseData.user?.role === 'analyst') resetToAnalytics();
        else resetToDashboard();
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

  async function submitMfaLogin(code: string) {
    if (!mfaChallenge) return;
    try {
      const response = await fetch(`${apiBaseUrl}/api/login/mfa`, {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({challenge_token: mfaChallenge, code: code.trim()}),
      });
      const data = await response.json().catch(() => null);
      if (!response.ok || !data?.access_token || !data?.refresh_token) {
        Alert.alert('Błąd', data?.detail || 'Nie udało się potwierdzić kodu.');
        return;
      }
      const loginRole: UserRole = isUserRole(data.user?.role) ? data.user.role : 'user';
      setRole(loginRole);
      setToken(data.access_token);
      setMfaChallenge(null);
      void AsyncStorage.setItem(ROLE_STORAGE_KEY, loginRole).catch(error => console.warn('Unable to save user role', error));
      await saveSessionTokens(data);
      if (data.user?.email) setUsername(data.user.email);
      if (loginRole === 'analyst') resetToAnalytics(); else resetToDashboard();
    } catch (error: any) {
      Alert.alert('Błąd sieci', error?.message || 'Nie udało się połączyć z serwerem.');
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
        body: JSON.stringify({
          email: data.email.trim(),
          password: data.password,
          captcha_token: data.captchaToken,
        }),
      });

      const responseData = await response.json().catch(() => null);

      if (response.ok && responseData) {
        if (responseData.access_token && responseData.refresh_token) {
          const registeredRole: UserRole = isUserRole(responseData.user?.role) ? responseData.user.role : 'user';
          setRole(registeredRole);
          void AsyncStorage.setItem(ROLE_STORAGE_KEY, registeredRole)
            .catch(error => console.warn('Unable to save user role', error));
          setToken(responseData.access_token);

          // Bezpieczne zapisanie tokena w Keychain
          await saveSessionTokens(responseData);
        }

        if (responseData.user && responseData.user.email) {
          setUsername(responseData.user.email);
        }

        if (responseData.user?.role === 'analyst') resetToAnalytics();
        else resetToDashboard();
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
      await logoutRemoteSession();
    } catch (e) {
      console.error('Błąd podczas wylogowywania:', e);
    } finally {
      // Usuwanie tokena z Keychain
      await clearSessionTokens();

      setToken(null);
      setRole(null);
      await AsyncStorage.removeItem(ROLE_STORAGE_KEY);
      setUsername('test user');
      resetToHome();
    }
  }

  async function getinfo() {
    if (!token) {
      Alert.alert('Błąd', 'Brak aktywnego tokenu. Zaloguj się ponownie.');
      goHome();
      return;
    }

    try {
      const response = await authenticatedFetch(`${apiBaseUrl}/api/me`, {
        method: 'GET',
        headers: {'Content-Type': 'application/json'},
        accessToken: token,
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

  async function loginWithPasskey() {
    try {
      await finishFederatedLogin(await signInWithPasskey());
    } catch (error) {
      Alert.alert('Logowanie passkey', error instanceof Error ? error.message : 'Nie udało się zalogować passkey.');
    }
  }

  async function loginWithGoogle() {
    try {
      await finishFederatedLogin(await signInWithGoogle());
    } catch (error) {
      Alert.alert('Logowanie Google', error instanceof Error ? error.message : 'Nie udało się zalogować przez Google.');
    }
  }

  return {
    screen,
    goBack,
    username,
    token,
    role,
    handleForbidden,
    goHome,
    goLogin,
    goRegister,
    goDashboard,
    goAnalytics: resetToAnalytics,
    goAnalyticsUsers: resetToAnalyticsUsers,
    goAnalyticsTransactions: resetToAnalyticsTransactions,
    goAnalyticsAuditEvents: resetToAnalyticsAuditEvents,
    goExchangeRates,
    goProfile,
    goQrScanner,
    goQrHub,
    goQrGeneration,
    goTransactionHistory,
    pendingTransactionId,
    clearPendingTransaction: () => setPendingTransactionId(null),
    openTransactionOnDashboard,
    submitLogin,
    mfaChallenge,
    submitMfaLogin,
    cancelMfaLogin: () => setMfaChallenge(null),
    submitRegister,
    loginWithPasskey,
    loginWithGoogle,
    logout,
    getinfo,
  };
}
