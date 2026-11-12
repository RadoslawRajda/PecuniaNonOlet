module.exports = {
  preset: '@react-native/jest-preset',
  moduleNameMapper: {
    '^lucide-react-native/icons/.*$': '<rootDir>/test-mocks/LucideIcon.tsx',
  },
};
