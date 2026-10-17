
import React from 'react';
import {
  View,
  Text,
  StyleSheet,
  StatusBar,
  TouchableOpacity,
  Vibration,
} from 'react-native';
import {
  SafeAreaProvider,
  SafeAreaView,
} from 'react-native-safe-area-context';


function App() {


  function loginButtonPressed()
  {
    Vibration.vibrate(100);
  }
  function registerButtonPressed()
  {
    Vibration.vibrate(1000);
  }
  return (
    <SafeAreaProvider>
      <StatusBar barStyle="light-content" backgroundColor="#101827" />

      <SafeAreaView style={styles.container}>
        <View style={styles.content}>
          <Text style={styles.emoji}>💵 💰 🤑 </Text>

          <Text style={styles.title}>
            Pecunia non olet
          </Text>

          <Text style={styles.subtitle}>
            Turbo bank
          </Text>

          <Text style={styles.dollars}>💸 💲 💸 </Text>

          <View style={styles.buttons}>
            <TouchableOpacity 
            style={styles.button} 
            activeOpacity={0.5} 
            onPress={() => {loginButtonPressed()}}>
              <Text style={styles.buttonText}>Zaloguj 💰💰💰 </Text>
            </TouchableOpacity>
            <TouchableOpacity 
            style={styles.button} 
            activeOpacity={0.5} 
            onPress={() => {registerButtonPressed()}}>
              <Text style={styles.buttonText}>Załóż konto🤑 </Text>
            </TouchableOpacity>
          </View>
        </View>

        <View style={styles.footer}>
          <Text style={styles.authorsTitle}>
            Autorzy
          </Text>

          <Text style={styles.authors}>
            Radosław Rajda{'\n'}
            Jakub Gnela{'\n'}
            Jakub Knapik
          </Text>
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#101827',
    paddingHorizontal: 24,
  },
  content: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emoji: {
    fontSize: 54,
    marginBottom: 30,
  },
  title: {
    fontSize: 36,
    fontWeight: 'bold',
    color: '#FACC15',
    textAlign: 'center',
  },
  subtitle: {
    fontSize: 17,
    color: '#CBD5E1',
    marginTop: 12,
    textAlign: 'center',
  },
  dollars: {
    fontSize: 35,
    marginTop: 36,
  },
  footer: {
    alignItems: 'center',
    paddingBottom: 35,
  },
  authorsTitle: {
    color: '#FACC15',
    fontSize: 16,
    fontWeight: 'bold',
    marginBottom: 10,
  },
  authors: {
    color: '#94A3B8',
    fontSize: 15,
    lineHeight: 26,
    textAlign: 'center',
  },
  buttons: {
    marginTop: 36,
    width: '100%',
    alignItems: 'center',
    gap: 20
  },

  button: {
    backgroundColor: '#FACC15',
    paddingVertical: 18,
    paddingHorizontal: 60,
    width: '80%',
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 5,
  },

  buttonText: {
    color: '#000000',
    fontSize: 20,
    fontWeight: 'bold',
  },
});

export default App;
