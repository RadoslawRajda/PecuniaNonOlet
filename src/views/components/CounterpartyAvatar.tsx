import React from 'react';
import {Image, StyleSheet, Text, View} from 'react-native';
import {API_URL} from '@env';
import {COLORS} from '../theme';

export function CounterpartyAvatar({token, email, transactionId, size = 52}: {token: string | null; email?: string | null; transactionId?: string; size?: number}) {
  const [photoUri, setPhotoUri] = React.useState<string | null>(null);
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  React.useEffect(() => {
    if (!token || (!email && !transactionId)) return;
    let active = true;
    const path = transactionId
      ? `/api/transactions/${encodeURIComponent(transactionId)}/counterparty-photo`
      : `/api/profile/photo/recipient?email=${encodeURIComponent(email ?? '')}`;
    fetch(`${apiBaseUrl}${path}`, {headers: {Authorization: `Bearer ${token}`}})
      .then(async response => {
        if (!response.ok) return null;
        const blob = await response.blob();
        return await new Promise<string>((resolve, reject) => {
          const reader = new FileReader();
          reader.onload = () => typeof reader.result === 'string' ? resolve(reader.result) : reject(new Error('Nie udało się odczytać zdjęcia.'));
          reader.onerror = () => reject(reader.error ?? new Error('Nie udało się odczytać zdjęcia.'));
          reader.readAsDataURL(blob);
        });
      })
      .then(uri => {if (active && uri) setPhotoUri(uri);})
      .catch(() => {});
    return () => {active = false;};
  }, [apiBaseUrl, email, token, transactionId]);

  return <View style={[styles.avatar, {width: size, height: size, borderRadius: size * 0.27}]}>
    {photoUri ? <Image source={{uri: photoUri}} style={styles.image} accessibilityLabel="Zdjęcie kontrahenta" /> : <Text style={[styles.letter, {fontSize: size * 0.61}]}>P</Text>}
  </View>;
}

const styles = StyleSheet.create({
  avatar: {overflow: 'hidden', alignItems: 'center', justifyContent: 'center', backgroundColor: COLORS.yellow},
  image: {width: '100%', height: '100%'},
  letter: {color: COLORS.darkText, fontWeight: '900'},
});
