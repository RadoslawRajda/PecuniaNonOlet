module.exports = {
  preset: '@react-native/jest-preset',
  moduleNameMapper: {
    '^@env$': '<rootDir>/test-mocks/env.js',
    '^lucide-react-native/icons/.*$': '<rootDir>/test-mocks/LucideIcon.tsx',
    '^react-native-app-auth$': '<rootDir>/test-mocks/react-native-app-auth.js',
    '^react-native-passkey$': '<rootDir>/test-mocks/react-native-passkey.js',
    '^@react-native-clipboard/clipboard$': '<rootDir>/test-mocks/clipboard.js',
  },
};
