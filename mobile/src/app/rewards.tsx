import { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { Card, colors, EmptyHint, SectionTitle } from '../components/ui';
import * as db from '../lib/db';

const PROFILE = 'default';

export default function RewardsScreen() {
  const [stars, setStars] = useState(0);
  const [events, setEvents] = useState<db.RewardEventRow[]>([]);

  const refresh = useCallback(async () => {
    const [total, latest] = await Promise.all([
      db.totalRewardStars(),
      db.listRewardEvents(PROFILE),
    ]);
    setStars(total);
    setEvents(latest);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Card style={styles.hero}>
        <Text style={styles.starCount}>⭐ {stars}</Text>
        <Text style={styles.muted}>
          星星只保存在这台设备上。奖励努力和完成练习，不奖励重复刷分。
        </Text>
      </Card>

      <Card>
        <SectionTitle>最近获得的奖励</SectionTitle>
        {events.length ? (
          events.map((event) => (
            <View key={event.dedupKey} style={styles.eventRow}>
              <View style={styles.eventInfo}>
                <Text style={styles.eventReason}>{event.reason}</Text>
                <Text style={styles.muted}>{new Date(event.createdAt).toLocaleString()}</Text>
              </View>
              <Text style={styles.eventAmount}>+{event.amount}</Text>
            </View>
          ))
        ) : (
          <EmptyHint>完成一节课后，这里会出现奖励记录。</EmptyHint>
        )}
      </Card>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  content: {
    padding: 16,
    gap: 14,
    paddingBottom: 40,
  },
  hero: {
    alignItems: 'center',
    gap: 10,
    paddingVertical: 26,
  },
  starCount: {
    fontSize: 46,
    fontWeight: '900',
    color: colors.star,
  },
  muted: {
    fontSize: 14,
    color: colors.sub,
    lineHeight: 21,
  },
  eventRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingVertical: 10,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.border,
  },
  eventInfo: {
    flex: 1,
    gap: 4,
  },
  eventReason: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  eventAmount: {
    fontSize: 20,
    fontWeight: '900',
    color: colors.star,
  },
});
