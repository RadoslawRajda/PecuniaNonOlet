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

export function BrandLogo({size = 82, showProfilePhoto = false}: {size?: number; showProfilePhoto?: boolean}) {
  const {profilePhotoRevision, profilePhotoDataUri, profilePhotoResolved} = useAppPreferences();
  const [photoUnavailable, setPhotoUnavailable] = React.useState(false);
  React.useEffect(() => {
    setPhotoUnavailable(false);
  }, [profilePhotoRevision]);

  return (
    <View style={[styles.logo, {width: size, height: size, borderRadius: size * 0.27}]}>
      {(!showProfilePhoto || (profilePhotoResolved && !profilePhotoDataUri)) ? <Text style={[styles.logoText, {fontSize: size * 0.61}]}>P</Text> : null}
      {showProfilePhoto && profilePhotoDataUri && !photoUnavailable ? (
      <Image
        accessibilityLabel="Zdjęcie profilowe"
        source={{uri: profilePhotoDataUri}}
        onError={event => {
          console.error('Profile photo failed to load', event.nativeEvent.error);
          setPhotoUnavailable(true);
        }}
        style={styles.logoImage}
      />
      ) : null}
    </View>
  );
}

export function ScreenHeader({title, subtitle}: {title: string; subtitle?: string}) {
  return (
    <View style={styles.screenHeader}>
      <View style={styles.screenHeaderText}>
        <Text style={styles.screenHeaderTitle}>{title}</Text>
        {subtitle ? <Text style={styles.screenHeaderSubtitle}>{subtitle}</Text> : null}
      </View>
      <BrandLogo size={42} />
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
      accessibilityLabel={title}
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
    borderRadius: 22,
    overflow: 'hidden',
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
  },
  screenHeader: {width: '100%', minHeight: 46, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 16, marginBottom: 14},
  screenHeaderText: {flex: 1, gap: 3},
  screenHeaderTitle: {color: COLORS.white, fontSize: 26, fontWeight: '800'},
  screenHeaderSubtitle: {color: COLORS.muted, fontSize: 14},
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
