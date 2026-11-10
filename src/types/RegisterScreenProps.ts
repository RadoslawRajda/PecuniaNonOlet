import type {RegisterData} from '../models/auth';

export type RegisterScreenProps = {
  onBack: () => void;
  onLogin: () => void;
  onSubmit: (data: RegisterData) => void;
};
