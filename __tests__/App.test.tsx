/**
 * @format
 */

import React from 'react';
import ReactTestRenderer from 'react-test-renderer';
import App from '../App';

jest.mock('react-native-keychain', () => ({
  ACCESSIBLE: {WHEN_UNLOCKED_THIS_DEVICE_ONLY: 'WHEN_UNLOCKED_THIS_DEVICE_ONLY'},
  getGenericPassword: jest.fn(async () => false),
  resetGenericPassword: jest.fn(async () => true),
  setGenericPassword: jest.fn(async () => true),
}));
jest.mock('@react-native-async-storage/async-storage', () => ({
  __esModule: true,
  default: {getItem: jest.fn(async () => null), setItem: jest.fn(async () => undefined), removeItem: jest.fn(async () => undefined)},
}));
jest.mock('react-native-permissions', () => ({
  PERMISSIONS: {IOS: {LOCATION_WHEN_IN_USE: 'ios.permission.LOCATION_WHEN_IN_USE'}, ANDROID: {ACCESS_COARSE_LOCATION: 'android.permission.ACCESS_COARSE_LOCATION'}},
  RESULTS: {GRANTED: 'granted', DENIED: 'denied', BLOCKED: 'blocked', UNAVAILABLE: 'unavailable'},
  check: jest.fn(async () => 'granted'),
  request: jest.fn(async () => 'granted'),
}));
jest.mock('react-native-geolocation-service', () => ({getCurrentPosition: jest.fn()}));
jest.mock('react-native-image-picker', () => ({launchImageLibrary: jest.fn()}));
jest.mock('react-native-webview', () => ({WebView: () => null}));
jest.mock('react-native-vision-camera', () => ({Camera: () => null, useCameraDevice: () => null, useCodeScanner: () => ({})}));
jest.mock('react-native-qrcode-svg', () => () => null);

test('renders correctly', async () => {
  await ReactTestRenderer.act(async () => {
    ReactTestRenderer.create(<App />);
    await new Promise<void>(resolve => setTimeout(resolve, 0));
  });
});
