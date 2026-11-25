export function isAllowedHttpsNavigation(url: string, allowedHosts: readonly string[]): boolean {
  try {
    const parsedUrl = new URL(url);
    return parsedUrl.protocol === 'https:'
      && allowedHosts.includes(parsedUrl.hostname)
      && !parsedUrl.username
      && !parsedUrl.password
      && !parsedUrl.port;
  } catch {
    return false;
  }
}
