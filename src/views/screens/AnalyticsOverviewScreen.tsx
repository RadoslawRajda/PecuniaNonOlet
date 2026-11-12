import React from 'react';
import {Text, View} from 'react-native';
import {AnalyticsPage, styles} from './AnalyticsPage';
import {useAnalyticsRequest} from './useAnalyticsRequest';

type Overview={users_total:number;users_by_role:Record<string,number>;active_sessions:number;transactions_total:number;transactions_by_kind:Record<string,number>;transactions_by_status:Record<string,number>};
export function AnalyticsOverviewScreen({token}:{token:string|null}) {
 const {data,loading,error,retry}=useAnalyticsRequest<Overview>(token,'/api/analytics/overview');
 const metrics=data?[{label:'Użytkownicy',value:data.users_total},{label:'Aktywne sesje',value:data.active_sessions},{label:'Wszystkie transakcje',value:data.transactions_total},{label:'Konta użytkowników',value:data.users_by_role.user??0},{label:'Konta analityków',value:data.users_by_role.analyst??0},{label:'Zakończone transakcje',value:data.transactions_by_status.completed??0},{label:'Odwrócone transakcje',value:data.transactions_by_status.reversed??0},{label:'Otwarcia rachunków',value:data.transactions_by_kind.opening??0},{label:'Przelewy',value:data.transactions_by_kind.transfer??0},{label:'Wymiany walut',value:data.transactions_by_kind.exchange??0}]:[];
 return <AnalyticsPage title="Przegląd" loading={loading} error={error} onRetry={retry}><View style={styles.grid}>{metrics.map(m=><View key={m.label} style={styles.metricCard}><Text style={styles.metricValue}>{m.value.toLocaleString('pl-PL')}</Text><Text style={styles.metricLabel}>{m.label}</Text></View>)}</View></AnalyticsPage>;
}
