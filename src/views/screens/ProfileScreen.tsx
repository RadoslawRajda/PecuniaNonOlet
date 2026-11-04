import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onChangeProfile: () => void;
  onBack: () => void;
};

export function ProfileScreen({onChangeProfile, onBack}: Props) {
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />

        <Text style={styles.title}>Profil</Text>

        <View style={styles.button}>
          <AppButton
            title="Zmień profil"
            onPress={onChangeProfile}
          />

          <AppButton
            title="Wróć do dashboardu"
            onPress={onBack}
            secondary
          />
        </View>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingVertical: 20,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 35,
  },
  title: {
    color: COLORS.yellow,
    fontSize: 30,
    fontWeight: '800',
    textAlign: 'center',
    marginTop: 30,
  },
  button: {
    width: '100%',
    marginTop: 48,
    gap: 14,
  },
});
