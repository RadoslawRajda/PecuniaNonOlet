import React from 'react';
import {Text, TextInput} from 'react-native';
import ReactTestRenderer from 'react-test-renderer';
import {LoginScreen} from '../src/views/screens/LoginScreen';

jest.mock('../src/context/AppPreferences', () => ({
  useAppPreferences: () => ({
    profilePhotoRevision: 0,
    profilePhotoDataUri: null,
    profilePhotoResolved: true,
  }),
}));

describe('MFA login input', () => {
  it('allows entering and submitting a recovery code', async () => {
    const submitMfa = jest.fn();
    let renderer!: ReactTestRenderer.ReactTestRenderer;

    await ReactTestRenderer.act(async () => {
      renderer = ReactTestRenderer.create(
        <LoginScreen
          onBack={jest.fn()}
          onRegister={jest.fn()}
          onSubmit={jest.fn()}
          onPasskey={jest.fn()}
          onGoogle={jest.fn()}
          mfaRequired
          onSubmitMfa={submitMfa}
        />,
      );
    });

    const toggle = renderer.root.findAll(node => {
      if (typeof node.props.onPress !== 'function') return false;
      return node.findAllByType(Text).some(textNode =>
        textNode.props.children === 'Użyj kodu odzyskiwania',
      );
    })[0];
    expect(toggle).toBeDefined();
    await ReactTestRenderer.act(async () => toggle?.props.onPress());

    const recoveryInput = renderer.root
      .findAllByType(TextInput)
      .find(input => input.props.accessibilityLabel === 'Kod odzyskiwania');
    expect(recoveryInput?.props.maxLength).toBe(22);
    const recoveryCode = 'ab_cd-123456789xyzABCD';
    await ReactTestRenderer.act(async () => recoveryInput?.props.onChangeText(recoveryCode));
    const submit = renderer.root.findByProps({accessibilityLabel: 'Potwierdź kod'});
    await ReactTestRenderer.act(async () => submit.props.onPress());
    expect(submitMfa).toHaveBeenCalledWith(recoveryCode);
  });
});
