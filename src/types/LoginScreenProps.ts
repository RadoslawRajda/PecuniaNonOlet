import type {LoginData} from '../models/auth';

export type LoginScreenProps = {
  onBack: () => void;
  onRegister: () => void;
  onSubmit: (data: LoginData) => void;
  onPasskey: () => void;
  onGoogle: () => void;
  mfaRequired?: boolean;
  onSubmitMfa?: (code: string) => void;
  onCancelMfa?: () => void;
};
