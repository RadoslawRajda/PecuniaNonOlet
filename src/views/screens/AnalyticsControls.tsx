import React from 'react';
import {Pressable, Text, View} from 'react-native';
import {FormInput} from '../components/Ui';
import {styles} from './AnalyticsPage';

export function ChoiceFilter({label, value, options, onChange}: {label:string; value:string; options:{label:string;value:string}[]; onChange:(value:string)=>void}) {
  return <View style={styles.choiceGroup}><Text style={styles.filterLabel}>{label}</Text><View style={styles.choices}>{options.map(option => <Pressable key={option.value || 'all'} accessibilityRole="button" accessibilityState={{selected:value===option.value}} onPress={()=>onChange(option.value)} style={[styles.choice,value===option.value&&styles.choiceSelected]}><Text style={[styles.choiceText,value===option.value&&styles.choiceTextSelected]}>{option.label}</Text></Pressable>)}</View></View>;
}
export function DateRangeFields({from,to,onFromChange,onToChange}:{from:string;to:string;onFromChange:(v:string)=>void;onToChange:(v:string)=>void}) {
  return <View style={styles.dateFields}><FormInput label="Od (RRRR-MM-DD)" value={from} onChangeText={onFromChange} placeholder="2026-01-31"/><FormInput label="Do (RRRR-MM-DD)" value={to} onChangeText={onToChange} placeholder="2026-12-31"/></View>;
}
export function formatDate(value:string) { const date=new Date(value); return Number.isNaN(date.getTime())?value:date.toLocaleString('pl-PL'); }
export function formatMinor(value:number|null,currency:string|null) { return value===null||!currency?'—':`${(value/100).toFixed(2)} ${currency}`; }
export const PAGE_SIZE=50;
export function analyticsPath(endpoint:string, params:Record<string,string>) { const query=new URLSearchParams(params); return `${endpoint}?${query.toString()}`; }
export function paginationParams(offset:number) { return {limit:String(PAGE_SIZE),offset:String(offset)}; }
export function dateParams(from:string,to:string) { const result:Record<string,string>={}; if(from)result.from=String(toTimestamp(from,false)); if(to)result.to=String(toTimestamp(to,true)); return result; }
export function validateDateRange(from:string,to:string,userId='') { if(userId&&(!/^\d+$/.test(userId)||Number(userId)<1))return 'ID użytkownika musi być dodatnią liczbą całkowitą.'; const start=from?toTimestamp(from,false):null; const end=to?toTimestamp(to,true):null; if(from&&start===null)return 'Data początkowa musi mieć format RRRR-MM-DD.'; if(to&&end===null)return 'Data końcowa musi mieć format RRRR-MM-DD.'; if(start!==null&&end!==null&&start>end)return 'Data początkowa nie może być późniejsza od końcowej.'; return null; }
function toTimestamp(value:string,end:boolean):number|null { if(!/^\d{4}-\d{2}-\d{2}$/.test(value))return null; const date=new Date(`${value}T${end?'23:59:59':'00:00:00'}Z`); return Number.isNaN(date.getTime())||date.toISOString().slice(0,10)!==value?null:Math.floor(date.getTime()/1000); }
