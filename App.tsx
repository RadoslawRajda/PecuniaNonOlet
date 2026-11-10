import React from 'react';
import {BackHandler, Pressable, StatusBar, StyleSheet, Text, View} from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
} from 'react-native-safe-area-context';

import {useAppController} from './src/controllers/useAppController';

import {HomeScreen} from './src/views/screens/HomeScreen';
import {LoginScreen} from './src/views/screens/LoginScreen';
import {RegisterScreen} from './src/views/screens/RegisterScreen';
import {Dashboard} from './src/views/screens/Dashboard';
import {ExchangeRatesScreen} from './src/views/screens/ExchangeRatesScreen';
import {ProfileScreen} from './src/views/screens/ProfileScreen';
import {QrScannerScreen} from './src/views/screens/QrScannerScreen';
import {QrGenerationScreen} from './src/views/screens/QrGenerationScreen';
import {TransactionHistoryScreen} from './src/views/screens/TransactionHistoryScreen';
import {Loading} from './src/views/screens/Loading';
import {QrHubScreen} from './src/views/screens/QrHubScreen';

import {COLORS, createThemedStyles} from './src/views/theme';
import {AppPreferencesProvider, useAppPreferences} from './src/context/AppPreferences';

function AppScreens({controller}: {controller: ReturnType<typeof useAppController>}) {
  const {colorScheme} = useAppPreferences();
  React.useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', () => controller.goBack());
    return () => subscription.remove();
  }, [controller.goBack]);
  const tabs = [
    {screen: 'dashboard', label: 'Pulpit', icon: '⌂', onPress: controller.goDashboard},
    {screen: 'transactionHistory', label: 'Historia', icon: '↕', onPress: controller.goTransactionHistory},
    {screen: 'exchangeRates', label: 'Wymiana', icon: '⇄', onPress: controller.goExchangeRates},
    {screen: 'qrHub', label: 'QR', icon: '▦', onPress: controller.goQrHub},
    {screen: 'profile', label: 'Profil', icon: '●', onPress: controller.goProfile},
  ] as const;
  const showNavigation = ['dashboard', 'transactionHistory', 'exchangeRates', 'qrScanner', 'qrHub', 'profile', 'qrGeneration'].includes(controller.screen);

  return (
    <SafeAreaProvider>
      <StatusBar
        barStyle={colorScheme === 'light' ? 'dark-content' : 'light-content'}
        backgroundColor={COLORS.background}
      />

      <SafeAreaView
        style={[styles.container, {backgroundColor: COLORS.background}]}
        edges={['top', 'bottom']}>

        <View style={styles.screenContent}>

        {controller.screen === 'loading' && <Loading/>}

        {controller.screen === 'home' && (
          <HomeScreen
            onLogin={controller.goLogin}
            onRegister={controller.goRegister}
          />
        )}

        {controller.screen === 'login' && (
          <LoginScreen
            onBack={controller.goHome}
            onRegister={controller.goRegister}
            onSubmit={controller.submitLogin}
            onPasskey={controller.loginWithPasskey}
          />
        )}

        {controller.screen === 'register' && (
          <RegisterScreen
            onBack={controller.goHome}
            onLogin={controller.goLogin}
            onSubmit={controller.submitRegister}
          />
        )}

        {controller.screen === 'dashboard' && (
          <Dashboard
            username={controller.username}
            token={controller.token}
            goHome={controller.goHome}
          />
        )}

        {controller.screen === 'exchangeRates' && (
          <ExchangeRatesScreen
            token={controller.token}
            goHome={controller.goHome}
          />
        )}

        {controller.screen === 'profile' && (
          <ProfileScreen
            onQrGeneration={controller.goQrGeneration}
            onLogout={controller.logout}
          />
        )}

        {controller.screen === 'qrScanner' && (
          <QrScannerScreen
            token={controller.token}
            goHome={controller.goHome}
          />
        )}

        {controller.screen === 'qrHub' && (
          <QrHubScreen onScan={controller.goQrScanner} onCreate={controller.goQrGeneration} />
        )}

        {controller.screen === 'qrGeneration' && (
          <QrGenerationScreen
            username={controller.username}
            token={controller.token}
          />
        )}

        {controller.screen === 'transactionHistory' && (
          <TransactionHistoryScreen
            token={controller.token}
            goHome={controller.goHome}
          />
        )}

        </View>
        {showNavigation && controller.token ? (
          <View style={styles.navbar}>
            {tabs.map(tab => {
              const active = controller.screen === tab.screen || (controller.screen === 'qrGeneration' && tab.screen === 'profile');
              return (
                <Pressable key={tab.screen} accessibilityRole="button" accessibilityState={{selected: active}} accessibilityLabel={tab.label} onPress={tab.onPress} style={styles.navItem}>
                  <Text style={[styles.navIcon, active && styles.navActive]}>{tab.icon}</Text>
                  <Text numberOfLines={1} style={[styles.navLabel, active && styles.navActive]}>{tab.label}</Text>
                </Pressable>
              );
            })}
          </View>
        ) : null}
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

function App() {
  const controller = useAppController();
  return (
    <AppPreferencesProvider token={controller.token}>
      <AppScreens controller={controller} />
    </AppPreferencesProvider>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
  screenContent: {flex: 1},
  navbar: {minHeight: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', backgroundColor: COLORS.surface, borderTopWidth: 1, borderTopColor: COLORS.border, paddingHorizontal: 4},
  navItem: {flex: 1, alignItems: 'center', justifyContent: 'center', minHeight: 60, gap: 3},
  navIcon: {color: COLORS.muted, fontSize: 21, fontWeight: '700'},
  navLabel: {color: COLORS.muted, fontSize: 10, fontWeight: '600'},
  navActive: {color: COLORS.yellow},
}));

export default App;
