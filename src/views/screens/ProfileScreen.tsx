import React from 'react';
import {
  Alert,
  Image,
  PermissionsAndroid,
  Platform,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import {
  launchImageLibrary,
  type ImageLibraryOptions,
} from 'react-native-image-picker';

import {AppButton, BrandLogo} from '../components/Ui';
import {COLORS} from '../theme';

type Props = {
  onBack: () => void;
};

export function ProfileScreen({onBack}: Props) {
  const [profileImageUri, setProfileImageUri] = React.useState<string | null>(
    null,
  );

  async function changeProfileImage() {
    if (Platform.OS === 'android') {
      const permission =
        Platform.Version >= 33
          ? PermissionsAndroid.PERMISSIONS.READ_MEDIA_IMAGES
          : PermissionsAndroid.PERMISSIONS.READ_EXTERNAL_STORAGE;
      const permissionResult = await PermissionsAndroid.request(permission);

      if (permissionResult !== PermissionsAndroid.RESULTS.GRANTED) {
        return;
      }
    }

    const options: ImageLibraryOptions = {
      mediaType: 'photo',
      selectionLimit: 1,
    };
    const result = await launchImageLibrary(options);

    if (result.didCancel) {
      return;
    }

    if (result.errorCode || !result.assets?.[0]?.uri) {
      Alert.alert(
        'Nie udało się zmienić zdjęcia',
        result.errorMessage ?? 'Nie wybrano poprawnego obrazu z galerii.',
      );
      return;
    }

    setProfileImageUri(result.assets[0].uri);
  }

  return (
    <ScrollView contentContainerStyle={styles.container}>
      <View style={styles.content}>
        {profileImageUri ? (
          <Image
            accessibilityLabel="Zdjęcie profilowe"
            source={{uri: profileImageUri}}
            style={styles.profileImage}
          />
        ) : (
          <BrandLogo />
        )}

        <Text style={styles.title}>Profil</Text>

        <View style={styles.button}>
          <AppButton
            title="Zmień profil"
            onPress={changeProfileImage}
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
  profileImage: {
    width: 82,
    height: 82,
    borderRadius: 22,
  },
  button: {
    width: '100%',
    marginTop: 48,
    gap: 14,
  },
});
