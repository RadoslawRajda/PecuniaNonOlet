import {isValidTotpProvisioningUri} from '../src/auth/totp';

describe('isValidTotpProvisioningUri', () => {
  it('accepts a TOTP provisioning URI with a secret', () => {
    expect(isValidTotpProvisioningUri('otpauth://totp/account%40example.com?secret=JBSWY3DPEHPK3PXP&issuer=Example')).toBe(true);
  });

  it.each([
    'https://example.com/?secret=JBSWY3DPEHPK3PXP',
    'otpauth://hotp/account?secret=JBSWY3DPEHPK3PXP',
    'otpauth://totp@evil.example/account?secret=JBSWY3DPEHPK3PXP',
    'otpauth://totp/account',
    'otpauth://totp/account?secret=',
    'otpauth://totp/account?secret=JBSWY3DPEHPK3PXP#fragment',
    null,
  ])('rejects invalid TOTP provisioning URI %s', uri => {
    expect(isValidTotpProvisioningUri(uri)).toBe(false);
  });
});
