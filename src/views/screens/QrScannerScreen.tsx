import React, {useCallback, useEffect, useState} from 'react';
import {
  Alert,
  ScrollView,
  StyleSheet,
  Text,
  View,
  Platform,
} from 'react-native';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import {
  PERMISSIONS,
  request,
  RESULTS,
} from 'react-native-permissions';
import {Camera, useCameraDevice} from 'react-native-vision-camera';
import {useCodeScanner} from 'react-native-vision-camera';
import {API_URL} from '@env';
import type {Account} from '../../types/Account';
import type {TransactionCreationFormValues} from '../../types/TransactionCreationFormValues';
import {TransactionCreation} from './TransactionCreation';
import {TransactionDetails} from './TransactionDetails';

type QrScannerProps = {token: string | null; goHome: () => void};

export function QrScannerScreen({token, goHome}: QrScannerProps) {
  const [cameraPermission, setCameraPermission] = useState<string>('pending');
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [initialValues, setInitialValues] = useState<TransactionCreationFormValues | null>(null);
  const [isCreationVisible, setCreationVisible] = useState(false);
  const [selectedTransactionId, setSelectedTransactionId] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const [hasProcessedCode, setHasProcessedCode] = useState(false);
  const cameraDevice = useCameraDevice('back');
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  useEffect(() => {
    if (!token) {
      return;
    }
    fetch(`${apiBaseUrl}/api/accounts`, {headers: {Authorization: `Bearer ${token}`}})
      .then(async response => {
        const data = await response.json().catch(() => null);
        if (!response.ok) {
          throw new Error(data?.detail || 'Nie udało się pobrać rachunków.');
        }
        setAccounts(data?.accounts ?? []);
      })
      .catch(error => setScanError(error instanceof Error ? error.message : 'Nie udało się pobrać rachunków.'));
  }, [apiBaseUrl, token]);

  const handleCodeScanned = useCallback(({value}: {value?: string}) => {
    if (hasProcessedCode || !value) {
      return;
    }
    let payment: {type?: string; version?: number; recipient_email?: string; currency_code?: string; amount?: string | number};
    try {
      payment = JSON.parse(value);
    } catch {
      setScanError('Ten kod QR nie zawiera danych płatności Pecunia.');
      return;
    }
    if (
      payment.type !== 'pecunia-payment' || payment.version !== 1 ||
      typeof payment.recipient_email !== 'string' ||
      !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(payment.recipient_email) ||
      typeof payment.currency_code !== 'string' ||
      !/^[A-Z]{3}$/.test(payment.currency_code) ||
      !/^\d+(\.\d{1,2})?$/.test(String(payment.amount)) ||
      Number(payment.amount) <= 0
    ) {
      setScanError('Dane płatności w kodzie QR są nieprawidłowe.');
      return;
    }
    const account = accounts.find(item => item.currency_code === payment.currency_code);
    if (!account) {
      setScanError(`Nie masz rachunku w walucie ${payment.currency_code}.`);
      return;
    }
    setHasProcessedCode(true);
    setScanError(null);
    setInitialValues({
      recipientEmail: payment.recipient_email,
      account,
      amount: String(payment.amount),
    });
    setCreationVisible(true);
  }, [accounts, hasProcessedCode]);

  const codeScanner = useCodeScanner({
    codeTypes: ['qr'],
    onCodeScanned: codes => {
      const value = codes.find(code => code.value)?.value;
      handleCodeScanned({value});
    },
  });

  const closeCreation = () => {
    setCreationVisible(false);
    setInitialValues(null);
    setHasProcessedCode(false);
  };

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
          {cameraPermission === RESULTS.GRANTED && cameraDevice ? (
            <Camera
              style={styles.camera}
              device={cameraDevice}
              isActive
              codeScanner={codeScanner}
            />
          ) : null}
          <View style={[styles.corner, styles.topLeft]} />
          <View style={[styles.corner, styles.topRight]} />
          <View style={[styles.corner, styles.bottomLeft]} />
          <View style={[styles.corner, styles.bottomRight]} />
        </View>
        {scanError ? <Text style={styles.scanError}>{scanError}</Text> : null}

      </View>
      <TransactionCreation
        visible={isCreationVisible}
        token={token}
        accounts={accounts}
        initialValues={initialValues}
        onClose={closeCreation}
        onCreated={transactionId => setSelectedTransactionId(transactionId ?? null)}
      />
      <TransactionDetails
        transactionId={selectedTransactionId}
        token={token}
        onClose={() => setSelectedTransactionId(null)}
        goHome={goHome}
      />
    </ScrollView>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
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
  scanError: {
    color: '#FCA5A5',
    fontSize: 14,
    marginTop: 16,
    textAlign: 'center',
  },
  scannerFrame: {
    width: 240,
    height: 240,
    marginTop: 36,
    position: 'relative',
    overflow: 'hidden',
  },
  camera: {
    ...StyleSheet.absoluteFill,
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
}));
