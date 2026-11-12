import React from 'react';
import {BackHandler, Pressable, StatusBar, StyleSheet, Text, View} from 'react-native';
import Home from 'lucide-react-native/icons/house';
import History from 'lucide-react-native/icons/rotate-ccw-clock';
import CircleDollarSign from 'lucide-react-native/icons/circle-dollar-sign';
import QrCode from 'lucide-react-native/icons/qr-code';
import UserRound from 'lucide-react-native/icons/user-round';
import ChartPie from 'lucide-react-native/icons/chart-pie';
import Users from 'lucide-react-native/icons/users';
import ArrowLeftRight from 'lucide-react-native/icons/arrow-left-right';
import ClipboardList from 'lucide-react-native/icons/clipboard-list';
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
import {AnalyticsOverviewScreen} from './src/views/screens/AnalyticsOverviewScreen';
import {AnalyticsUsersScreen} from './src/views/screens/AnalyticsUsersScreen';
import {AnalyticsTransactionsScreen} from './src/views/screens/AnalyticsTransactionsScreen';
import {AnalyticsAuditEventsScreen} from './src/views/screens/AnalyticsAuditEventsScreen';

import {COLORS, createThemedStyles} from './src/views/theme';
import {AppPreferencesProvider, useAppPreferences} from './src/context/AppPreferences';

function AppScreens({controller}: {controller: ReturnType<typeof useAppController>}) {
  const {colorScheme, preferencesLoaded} = useAppPreferences();
  const goBack = controller.goBack;
  React.useEffect(() => {
    const subscription = BackHandler.addEventListener('hardwareBackPress', goBack);
    return () => subscription.remove();
  }, [goBack]);
  if (!preferencesLoaded) return null;
  const userTabs = [
    {screen: 'dashboard', label: 'Pulpit', icon: Home, onPress: controller.goDashboard},
    {screen: 'transactionHistory', label: 'Historia', icon: History, onPress: controller.goTransactionHistory},
    {screen: 'exchangeRates', label: 'Wymiana', icon: CircleDollarSign, onPress: controller.goExchangeRates},
    {screen: 'qrHub', label: 'QR', icon: QrCode, onPress: controller.goQrHub},
    {screen: 'profile', label: 'Profil', icon: UserRound, onPress: controller.goProfile},

    //For testing access control
    // {screen: 'analytics', label: 'Przegląd', icon: ChartPie, onPress: controller.goAnalytics},
    // {screen: 'analyticsUsers', label: 'Użytk.', icon: Users, onPress: controller.goAnalyticsUsers},
    // {screen: 'analyticsTransactions', label: 'Transakcje', icon: ArrowLeftRight, onPress: controller.goAnalyticsTransactions},
    // {screen: 'analyticsAuditEvents', label: 'Audyt', icon: ClipboardList, onPress: controller.goAnalyticsAuditEvents},
  ] as const;
  const analystTabs = [
    {screen: 'analytics', label: 'Przegląd', icon: ChartPie, onPress: controller.goAnalytics},
    {screen: 'analyticsUsers', label: 'Użytk.', icon: Users, onPress: controller.goAnalyticsUsers},
    {screen: 'analyticsTransactions', label: 'Transakcje', icon: ArrowLeftRight, onPress: controller.goAnalyticsTransactions},
    {screen: 'analyticsAuditEvents', label: 'Audyt', icon: ClipboardList, onPress: controller.goAnalyticsAuditEvents},
    {screen: 'profile', label: 'Profil', icon: UserRound, onPress: controller.goProfile},

    //For testing access control
    // {screen: 'dashboard', label: 'Pulpit', icon: Home, onPress: controller.goDashboard},
    // {screen: 'transactionHistory', label: 'Historia', icon: History, onPress: controller.goTransactionHistory},
    // {screen: 'exchangeRates', label: 'Wymiana', icon: CircleDollarSign, onPress: controller.goExchangeRates},
    // {screen: 'qrHub', label: 'QR', icon: QrCode, onPress: controller.goQrHub},
  ] as const;
  const isAnalyst = controller.role === 'analyst';
  const tabs = isAnalyst ? analystTabs : userTabs;
  const showNavigation = isAnalyst
    ? ['analytics', 'analyticsUsers', 'analyticsTransactions', 'analyticsAuditEvents', 'profile'].includes(controller.screen)
    : ['dashboard', 'transactionHistory', 'exchangeRates', 'qrScanner', 'qrHub', 'profile', 'qrGeneration'].includes(controller.screen);

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

        {isAnalyst && controller.screen !== 'profile' ? (
          controller.screen === 'analyticsUsers' ? (
            <AnalyticsUsersScreen key={controller.screen} token={controller.token} />
          ) : controller.screen === 'analyticsTransactions' ? (
            <AnalyticsTransactionsScreen key={controller.screen} token={controller.token} />
          ) : controller.screen === 'analyticsAuditEvents' ? (
            <AnalyticsAuditEventsScreen key={controller.screen} token={controller.token} />
          ) : (
            <AnalyticsOverviewScreen key={controller.screen} token={controller.token} />
          )
        ) : <>

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
            initialTransactionId={controller.pendingTransactionId}
            onInitialTransactionShown={controller.clearPendingTransaction}
            goHome={controller.goHome}
            onExchange={controller.goExchangeRates}
            onQr={controller.goQrHub}
            onHistory={controller.goTransactionHistory}
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
            username={controller.username}
            role={controller.role}
            onLogout={controller.logout}
          />
        )}

        {controller.screen === 'qrScanner' && (
          <QrScannerScreen
            token={controller.token}
            onTransferCreated={controller.openTransactionOnDashboard}
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

        </>}

        </View>
        {showNavigation && controller.token ? (
          <View style={styles.navbar}>
            {tabs.map(tab => {
              const active = controller.screen === tab.screen || (controller.screen === 'qrGeneration' && tab.screen === 'profile');
              const Icon = tab.icon;
              return (
                <Pressable key={tab.screen} accessibilityRole="button" accessibilityState={{selected: active}} accessibilityLabel={tab.label} onPress={tab.onPress} style={styles.navItem}>
                  <Icon size={21} color={active ? COLORS.yellow : COLORS.muted} strokeWidth={2.2} />
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
    <AppPreferencesProvider token={controller.token} role={controller.role} handleForbidden={controller.handleForbidden}>
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
