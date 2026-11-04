import React from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';

export function Loading() {
  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />

        <Text style={styles.title}>
          Ładowanie...
        </Text>
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  container: {
    flexGrow: 1,
    paddingHorizontal: 24,
    paddingBottom: 28,
  },
  content: {
    flexGrow: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 55,
  },
  title: {
    color: COLORS.yellow,
    fontSize: 34,
    fontWeight: '800',
    textAlign: 'center',
    marginTop: 30,
  },
});