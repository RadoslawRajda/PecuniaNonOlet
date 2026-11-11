import React, {useEffect, useState} from 'react';
import {ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View} from 'react-native';
import {API_URL} from '@env';

import {AppButton, FormInput} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';
import {handleForbiddenResponse, useAppPreferences} from '../../context/AppPreferences';

type Page = 'overview' | 'users' | 'transactions' | 'auditEvents';
type Overview = {
  users_total: number;
  users_by_role: Record<string, number>;
  active_sessions: number;
  transactions_total: number;
  transactions_by_kind: Record<string, number>;
  transactions_by_status: Record<string, number>;
};
type AnalystUser = {id: number; email: string; role: string; created_at: string; accounts_count: number; transactions_count: number};
type AnalystTransaction = {
  id: string; kind: string; status: string; sender_user_id: number; sender_email: string;
  recipient_user_id: number | null; recipient_email: string | null; source_currency_code: string | null;
  destination_currency_code: string; source_amount_minor: number | null; destination_amount_minor: number;
  exchange_rate: string | null; created_at: string;
};
type AuditEvent = {
  id: number; actor_user_id: number | null; actor_role: string; action: string;
  entity_type: string; entity_id: string; details: Record<string, unknown>; created_at: string;
};
type PageData = {users?: AnalystUser[]; transactions?: AnalystTransaction[]; events?: AuditEvent[]; total?: number};
type Filters = {
  role: string; kind: string; status: string; transactionUserId: string; transactionFrom: string; transactionTo: string;
  action: string; entityType: string; actorUserId: string; auditFrom: string; auditTo: string;
};
const EMPTY_FILTERS: Filters = {
  role: '', kind: '', status: '', transactionUserId: '', transactionFrom: '', transactionTo: '',
  action: '', entityType: '', actorUserId: '', auditFrom: '', auditTo: '',
};

const PAGES: {id: Page; label: string}[] = [
  {id: 'overview', label: 'Przegląd'},
  {id: 'users', label: 'Użytkownicy'},
  {id: 'transactions', label: 'Transakcje'},
  {id: 'auditEvents', label: 'Zdarzenia audytu'},
];

export function AnalyticsOverviewScreen({token, onLogout}: {token: string | null; onLogout: () => void}) {
  const {handleForbidden} = useAppPreferences();
  const [page, setPage] = useState<Page>('overview');
  const [overview, setOverview] = useState<Overview | null>(null);
  const [pageData, setPageData] = useState<PageData>({});
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS);
  const [appliedFilters, setAppliedFilters] = useState<Filters>(EMPTY_FILTERS);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reloadKey, setReloadKey] = useState(0);
  const apiBaseUrl = (API_URL ?? '').trim().replace(/\/+$/, '');

  useEffect(() => {
    if (!token) {
      setError('Brak aktywnej sesji. Zaloguj się ponownie.');
      setLoading(false);
      return;
    }
    let active = true;
    const query = new URLSearchParams();
    let endpoint = '/api/analytics/overview';
    if (page === 'users') {
      endpoint = '/api/analytics/users';
      query.set('limit', '50');
      query.set('offset', String(offset));
      if (appliedFilters.role) query.set('role', appliedFilters.role);
    } else if (page === 'transactions') {
      endpoint = '/api/analytics/transactions';
      query.set('limit', '50');
      query.set('offset', String(offset));
      if (appliedFilters.kind) query.set('kind', appliedFilters.kind);
      if (appliedFilters.status) query.set('status', appliedFilters.status);
      if (appliedFilters.transactionUserId) query.set('user_id', appliedFilters.transactionUserId);
      addDateParams(query, appliedFilters.transactionFrom, appliedFilters.transactionTo);
    } else if (page === 'auditEvents') {
      endpoint = '/api/analytics/audit-events';
      query.set('limit', '50');
      query.set('offset', String(offset));
      if (appliedFilters.action) query.set('action', appliedFilters.action.trim());
      if (appliedFilters.entityType) query.set('entity_type', appliedFilters.entityType.trim());
      if (appliedFilters.actorUserId) query.set('actor_user_id', appliedFilters.actorUserId);
      addDateParams(query, appliedFilters.auditFrom, appliedFilters.auditTo);
    }
    const queryString = query.toString();
    const requestUrl = `${apiBaseUrl}${endpoint}${queryString ? `?${queryString}` : ''}`;
    setLoading(true);
    setError(null);
    fetch(requestUrl, {headers: {Authorization: `Bearer ${token}`}})
      .then(async response => {
        if (handleForbiddenResponse(response, handleForbidden)) return null;
        const data = await response.json().catch(() => null);
        if (!response.ok) throw new Error(data?.detail || 'Nie udało się pobrać danych analitycznych.');
        return data;
      })
      .then(data => {
        if (!active || !data) return;
        if (page === 'overview') setOverview(data as Overview);
        else setPageData(data as PageData);
      })
      .catch(loadError => {
        if (active) setError(loadError instanceof Error ? loadError.message : 'Nie udało się pobrać danych analitycznych.');
      })
      .finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [apiBaseUrl, appliedFilters, handleForbidden, offset, page, reloadKey, token]);

  const metrics = overview ? [
    {label: 'Użytkownicy', value: overview.users_total},
    {label: 'Aktywne sesje', value: overview.active_sessions},
    {label: 'Wszystkie transakcje', value: overview.transactions_total},
    {label: 'Konta użytkowników', value: overview.users_by_role.user ?? 0},
    {label: 'Konta analityków', value: overview.users_by_role.analyst ?? 0},
    {label: 'Zakończone transakcje', value: overview.transactions_by_status.completed ?? 0},
    {label: 'Odwrócone transakcje', value: overview.transactions_by_status.reversed ?? 0},
    {label: 'Otwarcia rachunków', value: overview.transactions_by_kind.opening ?? 0},
    {label: 'Przelewy', value: overview.transactions_by_kind.transfer ?? 0},
    {label: 'Wymiany walut', value: overview.transactions_by_kind.exchange ?? 0},
  ] : [];

  const changeFilter = (name: keyof Filters, value: string) => setFilters(current => ({...current, [name]: value}));
  const applyFilters = () => {
    const issue = validateFilters(page, filters);
    if (issue) {
      setError(issue);
      return;
    }
    setAppliedFilters({...filters});
    setOffset(0);
    setReloadKey(current => current + 1);
  };
  const clearFilters = () => {
    setFilters(EMPTY_FILTERS);
    setAppliedFilters(EMPTY_FILTERS);
    setOffset(0);
    setError(null);
    setReloadKey(current => current + 1);
  };

  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.content}>
          <Text style={styles.title}>Panel analityczny</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.navbar}>
            {PAGES.map(item => (
              <Pressable
                key={item.id}
                accessibilityRole="button"
                accessibilityState={{selected: page === item.id}}
                onPress={() => { setOffset(0); setPage(item.id); }}
                style={[styles.navItem, page === item.id && styles.navItemSelected]}>
                <Text style={[styles.navText, page === item.id && styles.navTextSelected]}>{item.label}</Text>
              </Pressable>
            ))}
          </ScrollView>

          <Text style={styles.sectionTitle}>{PAGES.find(item => item.id === page)?.label}</Text>
          {page !== 'overview' ? (
            <View style={styles.filterPanel}>
              <Text style={styles.filterTitle}>Filtry</Text>
              {page === 'users' ? (
                <ChoiceFilter label="Rola" value={filters.role} options={[
                  {label: 'Wszystkie', value: ''}, {label: 'Użytkownik', value: 'user'}, {label: 'Analityk', value: 'analyst'},
                ]} onChange={value => changeFilter('role', value)} />
              ) : null}
              {page === 'transactions' ? (
                <>
                  <ChoiceFilter label="Rodzaj transakcji" value={filters.kind} options={[
                    {label: 'Wszystkie', value: ''}, {label: 'Otwarcie', value: 'opening'}, {label: 'Przelew', value: 'transfer'}, {label: 'Wymiana', value: 'exchange'},
                  ]} onChange={value => changeFilter('kind', value)} />
                  <ChoiceFilter label="Status" value={filters.status} options={[
                    {label: 'Wszystkie', value: ''}, {label: 'Zakończona', value: 'completed'}, {label: 'Odwrócona', value: 'reversed'},
                  ]} onChange={value => changeFilter('status', value)} />
                  <FormInput label="ID użytkownika" value={filters.transactionUserId} onChangeText={value => changeFilter('transactionUserId', value)} keyboardType="number-pad" placeholder="np. 12" />
                  <DateRangeFields from={filters.transactionFrom} to={filters.transactionTo} onFromChange={value => changeFilter('transactionFrom', value)} onToChange={value => changeFilter('transactionTo', value)} />
                </>
              ) : null}
              {page === 'auditEvents' ? (
                <>
                  <FormInput label="Akcja" value={filters.action} onChangeText={value => changeFilter('action', value)} maxLength={64} placeholder="np. financial.transaction_completed" />
                  <FormInput label="Typ obiektu" value={filters.entityType} onChangeText={value => changeFilter('entityType', value)} maxLength={32} placeholder="np. transaction" />
                  <FormInput label="ID aktora" value={filters.actorUserId} onChangeText={value => changeFilter('actorUserId', value)} keyboardType="number-pad" placeholder="np. 12" />
                  <DateRangeFields from={filters.auditFrom} to={filters.auditTo} onFromChange={value => changeFilter('auditFrom', value)} onToChange={value => changeFilter('auditTo', value)} />
                </>
              ) : null}
              <View style={styles.filterButtons}>
                <View style={styles.filterButton}><AppButton title="Zastosuj" onPress={applyFilters} /></View>
                <View style={styles.filterButton}><AppButton title="Wyczyść" onPress={clearFilters} secondary /></View>
              </View>
            </View>
          ) : null}
          {loading ? <ActivityIndicator color={COLORS.yellow} size="large" /> : null}
          {error ? (
            <View style={styles.messageCard}>
              <Text style={styles.error}>{error}</Text>
              <AppButton title="Spróbuj ponownie" onPress={() => setReloadKey(current => current + 1)} secondary />
            </View>
          ) : null}

          {!loading && !error && page === 'overview' ? (
            <View style={styles.grid}>
              {metrics.map(metric => (
                <View key={metric.label} style={styles.metricCard}>
                  <Text style={styles.metricValue}>{metric.value.toLocaleString('pl-PL')}</Text>
                  <Text style={styles.metricLabel}>{metric.label}</Text>
                </View>
              ))}
            </View>
          ) : null}

          {!loading && !error && page === 'users' ? (
            <View style={styles.list}>
              <Text style={styles.muted}>Łącznie: {pageData.total ?? 0}</Text>
              {(pageData.users ?? []).map(user => (
                <View key={user.id} style={styles.dataCard}>
                  <Text style={styles.cardTitle}>{user.email}</Text>
                  <Text style={styles.cardText}>Rola: {user.role} · ID: {user.id}</Text>
                  <Text style={styles.cardText}>Rachunki: {user.accounts_count} · Transakcje: {user.transactions_count}</Text>
                  <Text style={styles.cardMuted}>Utworzono: {formatDate(user.created_at)}</Text>
                </View>
              ))}
              {pageData.users?.length === 0 ? <Text style={styles.muted}>Brak użytkowników.</Text> : null}
            </View>
          ) : null}

          {!loading && !error && page === 'transactions' ? (
            <View style={styles.list}>
              <Text style={styles.muted}>Łącznie: {pageData.total ?? 0}</Text>
              {(pageData.transactions ?? []).map(transaction => (
                <View key={transaction.id} style={styles.dataCard}>
                  <Text style={styles.cardTitle}>{transaction.kind} · {transaction.status}</Text>
                  <Text style={styles.cardText}>{transaction.sender_email}{transaction.recipient_email ? ` → ${transaction.recipient_email}` : ''}</Text>
                  <Text style={styles.cardText}>
                    {formatMinor(transaction.source_amount_minor, transaction.source_currency_code)} → {formatMinor(transaction.destination_amount_minor, transaction.destination_currency_code)}
                  </Text>
                  {transaction.exchange_rate ? <Text style={styles.cardText}>Kurs: {transaction.exchange_rate}</Text> : null}
                  <Text style={styles.cardMuted}>{formatDate(transaction.created_at)} · {transaction.id}</Text>
                </View>
              ))}
              {pageData.transactions?.length === 0 ? <Text style={styles.muted}>Brak transakcji.</Text> : null}
            </View>
          ) : null}

          {!loading && !error && page === 'auditEvents' ? (
            <View style={styles.list}>
              <Text style={styles.muted}>Łącznie: {pageData.total ?? 0}</Text>
              {(pageData.events ?? []).map(event => (
                <View key={event.id} style={styles.dataCard}>
                  <Text style={styles.cardTitle}>{event.action}</Text>
                  <Text style={styles.cardText}>Aktor: {event.actor_role}{event.actor_user_id ? ` · ID ${event.actor_user_id}` : ''}</Text>
                  <Text style={styles.cardText}>Obiekt: {event.entity_type} · {event.entity_id}</Text>
                  <Text style={styles.cardMuted}>{formatDate(event.created_at)}</Text>
                  <Text style={styles.details}>{JSON.stringify(event.details, null, 2)}</Text>
                </View>
              ))}
              {pageData.events?.length === 0 ? <Text style={styles.muted}>Brak zdarzeń audytu.</Text> : null}
            </View>
          ) : null}

          {!loading && !error && page !== 'overview' && (pageData.total ?? 0) > 50 ? (
            <View style={styles.pagination}>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{disabled: offset === 0}}
                disabled={offset === 0}
                onPress={() => setOffset(current => Math.max(0, current - 50))}
                style={[styles.pageButton, offset === 0 && styles.pageButtonDisabled]}>
                <Text style={styles.pageButtonText}>Poprzednia</Text>
              </Pressable>
              <Text style={styles.pageLabel}>Strona {Math.floor(offset / 50) + 1} z {Math.ceil((pageData.total ?? 0) / 50)}</Text>
              <Pressable
                accessibilityRole="button"
                accessibilityState={{disabled: offset + 50 >= (pageData.total ?? 0)}}
                disabled={offset + 50 >= (pageData.total ?? 0)}
                onPress={() => setOffset(current => current + 50)}
                style={[styles.pageButton, offset + 50 >= (pageData.total ?? 0) && styles.pageButtonDisabled]}>
                <Text style={styles.pageButtonText}>Następna</Text>
              </Pressable>
            </View>
          ) : null}

          <View style={styles.logout}>
            <AppButton title="Wyloguj się" onPress={onLogout} secondary />
          </View>
        </View>
      </ScrollView>
    </View>
  );
}

function formatDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('pl-PL');
}

function formatMinor(value: number | null, currency: string | null) {
  if (value === null || !currency) return '—';
  return `${(value / 100).toFixed(2)} ${currency}`;
}

function validateFilters(page: Page, filters: Filters): string | null {
  const userId = page === 'transactions' ? filters.transactionUserId : filters.actorUserId;
  if (userId && (!/^\d+$/.test(userId) || Number(userId) < 1)) return 'ID użytkownika musi być dodatnią liczbą całkowitą.';
  const from = page === 'transactions' ? filters.transactionFrom : filters.auditFrom;
  const to = page === 'transactions' ? filters.transactionTo : filters.auditTo;
  if (from && !dateToTimestamp(from, false)) return 'Data początkowa musi mieć format RRRR-MM-DD.';
  if (to && !dateToTimestamp(to, true)) return 'Data końcowa musi mieć format RRRR-MM-DD.';
  if (from && to && dateToTimestamp(from, false)! > dateToTimestamp(to, true)!) return 'Data początkowa nie może być późniejsza od końcowej.';
  return null;
}

function dateToTimestamp(value: string, endOfDay: boolean): number | null {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return null;
  const date = new Date(`${value}T${endOfDay ? '23:59:59' : '00:00:00'}Z`);
  if (Number.isNaN(date.getTime()) || date.toISOString().slice(0, 10) !== value) return null;
  return Math.floor(date.getTime() / 1000);
}

function addDateParams(query: URLSearchParams, from: string, to: string) {
  if (from) query.set('from', String(dateToTimestamp(from, false)));
  if (to) query.set('to', String(dateToTimestamp(to, true)));
}

function ChoiceFilter({label, value, options, onChange}: {
  label: string;
  value: string;
  options: {label: string; value: string}[];
  onChange: (value: string) => void;
}) {
  return (
    <View style={styles.choiceGroup}>
      <Text style={styles.filterLabel}>{label}</Text>
      <View style={styles.choices}>
        {options.map(option => (
          <Pressable key={option.value || 'all'} accessibilityRole="button" accessibilityState={{selected: value === option.value}} onPress={() => onChange(option.value)} style={[styles.choice, value === option.value && styles.choiceSelected]}>
            <Text style={[styles.choiceText, value === option.value && styles.choiceTextSelected]}>{option.label}</Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

function DateRangeFields({from, to, onFromChange, onToChange}: {
  from: string; to: string; onFromChange: (value: string) => void; onToChange: (value: string) => void;
}) {
  return (
    <View style={styles.dateFields}>
      <FormInput label="Od (RRRR-MM-DD)" value={from} onChangeText={onFromChange} placeholder="2026-01-31" />
      <FormInput label="Do (RRRR-MM-DD)" value={to} onChangeText={onToChange} placeholder="2026-12-31" />
    </View>
  );
}

const styles = createThemedStyles(() => StyleSheet.create({
  screen: {flex: 1},
  container: {flexGrow: 1, paddingHorizontal: 18, paddingVertical: 20},
  content: {alignItems: 'center', gap: 12, paddingBottom: 24},
  title: {color: COLORS.yellow, fontSize: 28, fontWeight: '800', textAlign: 'center', marginTop: 14, marginBottom: 4},
  navbar: {gap: 8, paddingVertical: 4},
  navItem: {backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 20, paddingHorizontal: 14, paddingVertical: 10},
  navItemSelected: {borderColor: COLORS.yellow, backgroundColor: '#302A16'},
  navText: {color: COLORS.muted, fontSize: 13, fontWeight: '700'},
  navTextSelected: {color: COLORS.yellow},
  sectionTitle: {alignSelf: 'stretch', color: COLORS.white, fontSize: 20, fontWeight: '700', marginTop: 8},
  filterPanel: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 14, padding: 14, gap: 12},
  filterTitle: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
  filterLabel: {color: COLORS.muted, fontSize: 13, fontWeight: '600'},
  choiceGroup: {gap: 8},
  choices: {flexDirection: 'row', flexWrap: 'wrap', gap: 6},
  choice: {borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, paddingHorizontal: 10, paddingVertical: 7},
  choiceSelected: {borderColor: COLORS.yellow, backgroundColor: '#302A16'},
  choiceText: {color: COLORS.muted, fontSize: 12, fontWeight: '600'},
  choiceTextSelected: {color: COLORS.yellow},
  dateFields: {gap: 10},
  filterButtons: {flexDirection: 'row', gap: 8},
  filterButton: {flex: 1},
  grid: {alignSelf: 'stretch', flexDirection: 'row', flexWrap: 'wrap', gap: 10},
  metricCard: {width: '48%', minHeight: 104, flexGrow: 1, justifyContent: 'center', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 14, padding: 14, gap: 6},
  metricValue: {color: COLORS.yellow, fontSize: 25, fontWeight: '800'},
  metricLabel: {color: COLORS.white, fontSize: 13, fontWeight: '600'},
  list: {alignSelf: 'stretch', gap: 10},
  dataCard: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 14, padding: 14, gap: 6},
  cardTitle: {color: COLORS.yellow, fontSize: 15, fontWeight: '800'},
  cardText: {color: COLORS.white, fontSize: 13},
  cardMuted: {color: COLORS.muted, fontSize: 12},
  details: {color: COLORS.muted, fontSize: 11, fontFamily: 'monospace'},
  muted: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 13},
  messageCard: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderRadius: 14, padding: 16, gap: 12},
  error: {color: '#FCA5A5', fontSize: 14},
  logout: {alignSelf: 'stretch', marginTop: 12},
  pagination: {alignSelf: 'stretch', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 4},
  pageButton: {borderColor: COLORS.border, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10},
  pageButtonDisabled: {opacity: 0.4},
  pageButtonText: {color: COLORS.white, fontSize: 12, fontWeight: '700'},
  pageLabel: {color: COLORS.muted, fontSize: 12, fontWeight: '600'},
}));
