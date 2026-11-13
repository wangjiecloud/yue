import { useCallback, useEffect, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';

import { BigButton, Card, colors, EmptyHint, SectionTitle } from '../components/ui';
import * as db from '../lib/db';
import { listInstalledCourses, type InstalledCourse } from '../lib/pack';

const PROFILE = 'default';

interface ReviewView {
  packageId: string;
  practiceId: string;
  reason: string;
  priority: number;
  course?: InstalledCourse;
  prompt?: string;
}

export default function ReviewScreen() {
  const [items, setItems] = useState<ReviewView[]>([]);
  const [loading, setLoading] = useState(true);

  const refresh = useCallback(async () => {
    const [reviewItems, courses] = await Promise.all([
      db.reviewList(PROFILE),
      listInstalledCourses(),
    ]);
    const byPackage = new Map(courses.map((course) => [course.row.packageId, course]));
    setItems(
      reviewItems.map((item) => {
        const course = byPackage.get(item.packageId);
        const practice = course?.course.practices.find(
          (candidate) => candidate.practiceId === item.practiceId,
        );
        return { ...item, course, prompt: practice?.prompt };
      }),
    );
    setLoading(false);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      <Text style={styles.intro}>
        复习结果只是学习辅助，不代表已经掌握。答错或用了提示的练习会出现在这里。
      </Text>
      {loading ? <Text style={styles.muted}>正在整理待复习内容…</Text> : null}
      {!loading && !items.length ? (
        <Card>
          <EmptyHint>目前没有待复习的练习，继续学习新课程吧。</EmptyHint>
        </Card>
      ) : null}
      {items.map((item) => {
        const title = item.course?.row.title ?? item.packageId;
        return (
          <Card key={`${item.packageId}:${item.practiceId}`} style={styles.card}>
            <SectionTitle>{title}</SectionTitle>
            <Text style={styles.reason}>{item.reason}</Text>
            {item.prompt ? <Text style={styles.prompt}>{item.prompt}</Text> : null}
            {item.course ? (
              <BigButton
                title="再练一次"
                onPress={() =>
                  router.push({
                    pathname: '/lesson/[packageId]',
                    params: { packageId: item.course!.row.packageId },
                  })
                }
              />
            ) : (
              <Text style={styles.muted}>课程包已删除，请让家长重新导入。</Text>
            )}
          </Card>
        );
      })}
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
  intro: {
    fontSize: 14,
    color: colors.sub,
    lineHeight: 21,
  },
  muted: {
    fontSize: 14,
    color: colors.sub,
  },
  card: {
    gap: 10,
  },
  reason: {
    fontSize: 15,
    color: colors.text,
    lineHeight: 22,
  },
  prompt: {
    fontSize: 20,
    fontWeight: '800',
    color: colors.text,
  },
});
