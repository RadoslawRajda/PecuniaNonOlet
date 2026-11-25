import {isAllowedHttpsNavigation} from '../src/views/webViewSecurity';

describe('isAllowedHttpsNavigation', () => {
  it('allows HTTPS navigation to explicitly approved hosts', () => {
    expect(isAllowedHttpsNavigation('https://nbp.pl/kursy', ['nbp.pl'])).toBe(true);
    expect(isAllowedHttpsNavigation('https://pecunianonolet.local/', ['pecunianonolet.local'])).toBe(true);
  });

  it.each([
    'http://nbp.pl/kursy',
    'https://nbp.pl.evil.example/kursy',
    'https://user@nbp.pl/kursy',
    'https://nbp.pl:8443/kursy',
    // eslint-disable-next-line no-script-url
    'javascript:alert(1)',
    'not a URL',
  ])('rejects untrusted navigation URL %s', url => {
    expect(isAllowedHttpsNavigation(url, ['nbp.pl'])).toBe(false);
  });
});
