export type ScreenName = 'home' | 'login' | 'register' | 'dashboard';

export type LoginData = {
  email: string;
  password: string;
};

export type RegisterData = {
  email: string;
  password: string;
  confirmPassword: string;
};

export function validateLogin(data: LoginData): string | null {
  if (!data.email.trim()) {
    return 'Podaj login lub adres e-mail.';
  }

  if (!data.password) {
    return 'Podaj hasło.';
  }

  return null;
}

export function validateRegister(
  data: RegisterData,
): string | null {
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(data.email.trim())) {
    return 'Podaj poprawny adres e-mail.';
  }

  if (data.password.length < 8) {
    return 'Hasło musi mieć minimum 8 znaków.';
  }

  if (data.password !== data.confirmPassword) {
    return 'Hasła nie są identyczne.';
  }

  return null;
}