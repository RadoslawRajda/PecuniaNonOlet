import React from 'react';
import {ActivityIndicator, ScrollView, StyleSheet, Text, View} from 'react-native';
import {AppButton, ScreenHeader} from '../components/Ui';
import {COLORS, createThemedStyles} from '../theme';

export function AnalyticsPage({title, loading, error, onRetry, children}: {
  title: string;
  loading: boolean;
  error: string | null;
  onRetry: () => void;
  children: React.ReactNode;
}) {
  return (
    <View style={styles.screen}>
      <ScrollView contentContainerStyle={styles.container}>
        <View style={styles.content}>
          <ScreenHeader title={title} />
          {children}
          {loading ? <ActivityIndicator color={COLORS.yellow} size="large" style={styles.loader} /> : null}
          {error ? <View style={styles.messageCard}>
            <Text style={styles.error}>{error}</Text>
            <AppButton title="Spróbuj ponownie" onPress={onRetry} secondary />
          </View> : null}
        </View>
      </ScrollView>
    </View>
  );
}

export const styles = createThemedStyles(() => StyleSheet.create({
  screen: {flex: 1},
  container: {flexGrow: 1, paddingHorizontal: 22, paddingTop: 18, paddingBottom: 24},
  content: {alignItems: 'stretch', gap: 14, paddingBottom: 24},
  grid: {alignSelf: 'stretch', flexDirection: 'row', flexWrap: 'wrap', gap: 10},
  metricCard: {width: '47%', minHeight: 108, flexGrow: 1, justifyContent: 'center', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, padding: 16, gap: 8},
  metricValue: {color: COLORS.yellow, fontSize: 27, fontWeight: '800'},
  metricLabel: {color: COLORS.muted, fontSize: 13, fontWeight: '600'},
  filterPanel: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, padding: 16, gap: 14},
  filterTitle: {color: COLORS.white, fontSize: 16, fontWeight: '700'},
  filterLabel: {color: COLORS.muted, fontSize: 13, fontWeight: '600'},
  choiceGroup: {gap: 8},
  choices: {flexDirection: 'row', flexWrap: 'wrap', gap: 6},
  choice: {minHeight: 36, justifyContent: 'center', borderColor: COLORS.border, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 7},
  choiceSelected: {borderColor: COLORS.yellow, backgroundColor: COLORS.yellow},
  choiceText: {color: COLORS.muted, fontSize: 12, fontWeight: '600'},
  choiceTextSelected: {color: COLORS.darkText},
  dateFields: {gap: 10},
  filterButtons: {flexDirection: 'row', gap: 8},
  filterButton: {flex: 1},
  list: {alignSelf: 'stretch', gap: 10},
  dataCard: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, padding: 16, gap: 7},
  cardTitle: {color: COLORS.yellow, fontSize: 15, fontWeight: '800'},
  cardText: {color: COLORS.white, fontSize: 13},
  cardMuted: {color: COLORS.muted, fontSize: 12},
  details: {color: COLORS.muted, fontSize: 11, fontFamily: 'monospace'},
  muted: {alignSelf: 'stretch', color: COLORS.muted, fontSize: 13},
  messageCard: {alignSelf: 'stretch', backgroundColor: COLORS.surface, borderColor: COLORS.border, borderWidth: 1, borderRadius: 16, padding: 16, gap: 12},
  loader: {alignSelf: 'center', marginVertical: 18},
  error: {color: '#FCA5A5', fontSize: 14},
  pagination: {alignSelf: 'stretch', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8, marginTop: 4},
  pageButton: {borderColor: COLORS.border, borderWidth: 1, borderRadius: 10, paddingHorizontal: 12, paddingVertical: 10},
  pageButtonDisabled: {opacity: 0.4},
  pageButtonText: {color: COLORS.white, fontSize: 12, fontWeight: '700'},
  pageLabel: {color: COLORS.muted, fontSize: 12, fontWeight: '600'},
}));
