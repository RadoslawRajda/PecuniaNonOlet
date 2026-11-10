import React from 'react';
import {
  Image,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import {useAppPreferences} from '../../context/AppPreferences';
import {COLORS, createThemedStyles} from '../theme';
import type {ButtonProps} from '../../types/ButtonProps';
import type {FormInputProps} from '../../types/FormInputProps';

export function BrandLogo() {
  const {profilePhotoRevision, profilePhotoDataUri} = useAppPreferences();
  const [photoUnavailable, setPhotoUnavailable] = React.useState(false);
  const [photoLoaded, setPhotoLoaded] = React.useState(false);
  React.useEffect(() => {
    setPhotoUnavailable(false);
    setPhotoLoaded(false);
  }, [profilePhotoRevision]);

  return (
    <View style={styles.logo}>
      <Text style={styles.logoText}>P</Text>
      {profilePhotoDataUri && !photoUnavailable ? (
      <Image
        accessibilityLabel="Zdjęcie profilowe"
        source={{uri: profilePhotoDataUri}}
        onLoad={() => {
          console.info('Profile photo loaded');
          setPhotoLoaded(true);
        }}
        onError={event => {
          console.error('Profile photo failed to load', event.nativeEvent.error);
          setPhotoUnavailable(true);
        }}
        style={[styles.logoImage, {opacity: photoLoaded ? 1 : 0}]}
      />
      ) : null}
    </View>
  );
}

export function AppButton({
  title,
  onPress,
  secondary = false,
}: ButtonProps) {
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({pressed}) => [
        styles.button,
        secondary && styles.secondaryButton,
        pressed && styles.pressed,
      ]}>
      <Text
        style={[
          styles.buttonText,
          secondary && styles.secondaryText,
        ]}>
        {title}
      </Text>
    </Pressable>
  );
}

export function FormInput({
  label,
  style,
  ...props
}: FormInputProps) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>

      <TextInput
        {...props}
        accessibilityLabel={label}
        placeholderTextColor={COLORS.muted}
        selectionColor={COLORS.yellow}
        style={[styles.input, style]}
      />
    </View>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  logo: {
    width: 82,
    height: 82,
    borderRadius: 22,
    backgroundColor: COLORS.yellow,
    justifyContent: 'center',
    alignItems: 'center',
  },
  logoText: {
    fontSize: 50,
    fontWeight: '900',
    color: COLORS.darkText,
  },
  logoImage: {
    ...StyleSheet.absoluteFill,
    width: 82,
    height: 82,
    borderRadius: 22,
  },
  button: {
    backgroundColor: COLORS.yellow,
    borderRadius: 12,
    minHeight: 58,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 16,
  },
  secondaryButton: {
    backgroundColor: 'transparent',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  pressed: {
    opacity: 0.75,
  },
  buttonText: {
    color: COLORS.darkText,
    fontSize: 17,
    fontWeight: '700',
    textAlign: 'center',
  },
  secondaryText: {
    color: COLORS.white,
  },
  field: {
    gap: 9,
  },
  label: {
    color: COLORS.muted,
    fontSize: 15,
    fontWeight: '500',
  },
  input: {
    height: 58,
    backgroundColor: COLORS.input,
    borderRadius: 12,
    paddingHorizontal: 18,
    color: COLORS.white,
    fontSize: 17,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
}));
