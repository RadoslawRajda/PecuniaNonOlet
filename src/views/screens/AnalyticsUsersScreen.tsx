import React,{useState} from 'react';
import {Text,View,Pressable} from 'react-native';
import {AnalyticsPage,styles} from './AnalyticsPage';
import {useAnalyticsRequest} from './useAnalyticsRequest';
import {AppButton} from '../components/Ui';
import {ChoiceFilter,analyticsPath,paginationParams,PAGE_SIZE} from './AnalyticsControls';

type User={id:number;email:string;role:string;created_at:string;accounts_count:number;transactions_count:number};
type Result={users:User[];total:number};
export function AnalyticsUsersScreen({token}:{token:string|null}) {
 const [role,setRole]=useState(''); const [appliedRole,setAppliedRole]=useState(''); const [offset,setOffset]=useState(0);
 const params={...paginationParams(offset),...(appliedRole?{role:appliedRole}:{})};
 const {data,loading,error,retry,setError}=useAnalyticsRequest<Result>(token,analyticsPath('/api/analytics/users',params));
 const apply=()=>{setOffset(0);setAppliedRole(role);retry();}; const clear=()=>{setRole('');setAppliedRole('');setOffset(0);setError(null);retry();};
 const total=data?.total??0;
 return <AnalyticsPage title="Użytkownicy" loading={loading} error={error} onRetry={retry}><View style={styles.filterPanel}><Text style={styles.filterTitle}>Filtry</Text><ChoiceFilter label="Rola" value={role} options={[{label:'Wszystkie',value:''},{label:'Użytkownik',value:'user'},{label:'Analityk',value:'analyst'}]} onChange={setRole}/><View style={styles.filterButtons}><View style={styles.filterButton}><AppButton title="Zastosuj" onPress={apply}/></View><View style={styles.filterButton}><AppButton title="Wyczyść" onPress={clear} secondary/></View></View></View>{!loading&&!error?<View style={styles.list}><Text style={styles.muted}>Łącznie: {total}</Text>{(data?.users??[]).map(u=><View key={u.id} style={styles.dataCard}><Text style={styles.cardTitle}>{u.email}</Text><Text style={styles.cardText}>Rola: {u.role} · ID: {u.id}</Text><Text style={styles.cardText}>Rachunki: {u.accounts_count} · Transakcje: {u.transactions_count}</Text><Text style={styles.cardMuted}>Utworzono: {new Date(u.created_at).toLocaleString('pl-PL')}</Text></View>)}{data?.users.length===0?<Text style={styles.muted}>Brak użytkowników.</Text>:null}{total>PAGE_SIZE?<View style={styles.pagination}><Pressable accessibilityRole="button" disabled={!offset} onPress={()=>setOffset(Math.max(0,offset-PAGE_SIZE))} style={[styles.pageButton,!offset&&styles.pageButtonDisabled]}><Text style={styles.pageButtonText}>Poprzednia</Text></Pressable><Text style={styles.pageLabel}>Strona {Math.floor(offset/PAGE_SIZE)+1} z {Math.ceil(total/PAGE_SIZE)}</Text><Pressable accessibilityRole="button" disabled={offset+PAGE_SIZE>=total} onPress={()=>setOffset(offset+PAGE_SIZE)} style={[styles.pageButton,offset+PAGE_SIZE>=total&&styles.pageButtonDisabled]}><Text style={styles.pageButtonText}>Następna</Text></Pressable></View>:null}</View>:null}</AnalyticsPage>;
}
