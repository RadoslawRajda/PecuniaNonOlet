export type ColorScheme = 'dark' | 'light' | 'pink' | 'blue' | 'blackAndWhite' | 'highContrast';

export const COLORS = {
  background: '#101827',
  surface: '#202631',
  input: '#2B3342',
  yellow: '#FACC15',
  white: '#F8FAFC',
  muted: '#94A3B8',
  border: '#3B4555',
  darkText: '#101827',
};

const DARK_COLORS = {...COLORS};
const LIGHT_COLORS = {
  background: '#F1F5F9',
  surface: '#FFFFFF',
  input: '#E2E8F0',
  yellow: '#B77900',
  white: '#172033',
  muted: '#64748B',
  border: '#CBD5E1',
  darkText: '#FFFFFF',
};

const SCHEMES: Record<ColorScheme, typeof COLORS> = {
  dark: DARK_COLORS,
  light: LIGHT_COLORS,
  pink: {background: '#24121F', surface: '#382033', input: '#4A2942', yellow: '#FF75B5', white: '#FFF1F7', muted: '#D4A9BD', border: '#70445E', darkText: '#24121F'},
  blue: {background: '#0B1B33', surface: '#142B4A', input: '#1D3A5F', yellow: '#55B8FF', white: '#EFF8FF', muted: '#A4BCD4', border: '#345477', darkText: '#0B1B33'},
  blackAndWhite: {background: '#000000', surface: '#111111', input: '#202020', yellow: '#FFFFFF', white: '#FFFFFF', muted: '#D0D0D0', border: '#FFFFFF', darkText: '#000000'},
  highContrast: {background: '#000000', surface: '#000000', input: '#000000', yellow: '#FFFF00', white: '#FFFFFF', muted: '#FFFFFF', border: '#FFFF00', darkText: '#000000'},
};

let styleRevision = 0;

export function setColorScheme(scheme: ColorScheme) {
  Object.assign(COLORS, SCHEMES[scheme] ?? DARK_COLORS);
  styleRevision += 1;
}

export function createThemedStyles<T extends Record<string, unknown>>(
  createStyles: () => T,
): T {
  let revision = -1;
  let styles: T;
  return new Proxy({} as T, {
    get(_target, property: string | symbol) {
      if (revision !== styleRevision) {
        styles = createStyles();
        revision = styleRevision;
      }
      return Reflect.get(styles!, property);
    },
  });
}
