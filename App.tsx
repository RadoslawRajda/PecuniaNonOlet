import React from 'react';
import {StatusBar, StyleSheet} from 'react-native';

import {
  SafeAreaProvider,
  SafeAreaView,
} from 'react-native-safe-area-context';

import {useAppController} from './src/controllers/useAppController';

import {HomeScreen} from './src/views/screens/HomeScreen';
import {LoginScreen} from './src/views/screens/LoginScreen';
import {RegisterScreen} from './src/views/screens/RegisterScreen';
import {Dashboard} from './src/views/screens/Dashboard';

import {COLORS} from './src/views/theme';

function App() {
  const controller = useAppController();

  return (
    <SafeAreaProvider>
      <StatusBar
        barStyle="light-content"
        backgroundColor={COLORS.background}
      />

      <SafeAreaView
        style={styles.container}
        edges={['top', 'bottom']}>

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
            onBack={controller.goHome}
            username={controller.username}
          />
        )}

      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.background,
  },
});

export default App;