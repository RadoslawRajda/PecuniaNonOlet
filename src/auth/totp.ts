export function isValidTotpProvisioningUri(value: unknown): value is string {
  if (typeof value !== 'string') return false;

  try {
    const uri = new URL(value);
    return uri.protocol === 'otpauth:'
      && uri.hostname === 'totp'
      && !uri.username
      && !uri.password
      && !uri.port
      && uri.pathname.length > 1
      && Boolean(uri.searchParams.get('secret'))
      && !uri.hash;
  } catch {
    return false;
  }
}
