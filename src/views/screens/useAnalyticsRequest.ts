import {useCallback, useEffect, useState} from 'react';
import {API_URL} from '@env';
import {handleForbiddenResponse, useAppPreferences} from '../../context/AppPreferences';

export function useAnalyticsRequest<T>(token: string | null, path: string) {
  const {handleForbidden} = useAppPreferences();
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const retry = useCallback(() => setReloadKey(key => key + 1), []);

  useEffect(() => {
    let active = true;
    if (!token) {
      setError('Brak aktywnej sesji. Zaloguj się ponownie.');
      setLoading(false);
      return () => { active = false; };
    }
    const baseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');
    setLoading(true);
    setError(null);
    fetch(`${baseUrl}${path}`, {headers: {Authorization: `Bearer ${token}`}})
      .then(async response => {
        if (handleForbiddenResponse(response, handleForbidden)) return null;
        const body = await response.json().catch(() => null);
        if (!response.ok) throw new Error(body?.detail || 'Nie udało się pobrać danych analitycznych.');
        return body as T;
      })
      .then(result => { if (active && result) setData(result); })
      .catch(loadError => { if (active) setError(loadError instanceof Error ? loadError.message : 'Nie udało się pobrać danych analitycznych.'); })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [handleForbidden, path, reloadKey, token]);

  return {data, loading, error, retry, setError};
}
