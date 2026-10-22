import React from 'react';
import {
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
  type TextInputProps,
} from 'react-native';
import {COLORS} from '../theme';

export function BrandLogo() {
  return (
    <View style={styles.logo}>
      <Text style={styles.logoText}>P</Text>
    </View>
  );
}

type ButtonProps = {
  title: string;
  onPress: () => void;
  secondary?: boolean;
};

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

type FormInputProps = TextInputProps & {
  label: string;
};

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

const styles = StyleSheet.create({
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
});