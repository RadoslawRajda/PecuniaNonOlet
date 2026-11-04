import React, {useEffect, useState} from 'react';
import {
  ScrollView,
  StyleSheet,
  Text,
  View,
  Platform,
} from 'react-native';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';
import {
  PERMISSIONS,
  request,
  RESULTS,
} from 'react-native-permissions';

type Props = {
  onBack: () => void;
};

export function QrScannerScreen({onBack}: Props) {
  const [cameraPermission, setCameraPermission] = useState<string>('pending');

  useEffect(() => {
    const permission =
      Platform.OS === 'ios'
        ? PERMISSIONS.IOS.CAMERA
        : PERMISSIONS.ANDROID.CAMERA;

    request(permission)
      .then(status => setCameraPermission(status))
      .catch(error => {
        console.error('Nie udało się poprosić o dostęp do kamery:', error);
        setCameraPermission(RESULTS.UNAVAILABLE);
      });
  }, []);

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        <BrandLogo />

        <Text style={styles.title}>Skaner QR</Text>
        <Text style={styles.description}>
          Umieść kod QR w ramce, aby go zeskanować.
        </Text>
        <Text style={styles.permissionStatus}>
          {cameraPermission === RESULTS.GRANTED
            ? 'Dostęp do kamery przyznany'
            : cameraPermission === 'pending'
              ? 'Prośba o dostęp do kamery...'
              : 'Brak dostępu do kamery'}
        </Text>

        <View style={styles.scannerFrame}>
          <View style={[styles.corner, styles.topLeft]} />
          <View style={[styles.corner, styles.topRight]} />
          <View style={[styles.corner, styles.bottomLeft]} />
          <View style={[styles.corner, styles.bottomRight]} />
        </View>

        <View style={styles.button}>
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
  description: {
    color: COLORS.muted,
    fontSize: 15,
    textAlign: 'center',
    marginTop: 12,
  },
  permissionStatus: {
    color: COLORS.muted,
    fontSize: 14,
    marginTop: 8,
  },
  scannerFrame: {
    width: 240,
    height: 240,
    marginTop: 36,
    position: 'relative',
  },
  corner: {
    width: 42,
    height: 42,
    position: 'absolute',
    borderColor: COLORS.yellow,
  },
  topLeft: {
    top: 0,
    left: 0,
    borderTopWidth: 4,
    borderLeftWidth: 4,
  },
  topRight: {
    top: 0,
    right: 0,
    borderTopWidth: 4,
    borderRightWidth: 4,
  },
  bottomLeft: {
    bottom: 0,
    left: 0,
    borderBottomWidth: 4,
    borderLeftWidth: 4,
  },
  bottomRight: {
    bottom: 0,
    right: 0,
    borderBottomWidth: 4,
    borderRightWidth: 4,
  },
  button: {
    width: '100%',
    marginTop: 48,
  },
});
