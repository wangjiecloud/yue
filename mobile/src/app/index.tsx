import { useCallback, useEffect, useState } from 'react';
import { Alert, Pressable, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import * as DocumentPicker from 'expo-document-picker';

import { Badge, BigButton, Card, colors, EmptyHint } from '../components/ui';
import { cleanupInterruptedImports, importPack, listInstalledCourses, sweepOrphanCourseDirs, type InstalledCourse } from '../lib/pack';
import { ensureDemoCourse } from '../lib/demo';
import { reviewList, totalRewardStars } from '../lib/db';

const PROFILE = 'default';

const SUBJECT_LABEL: Record<string, string> = {
  math: '数学',
  chinese: '语文',
  english: '英语',
};

export default function HomeScreen() {
  const [courses, setCourses] = useState<InstalledCourse[]>([]);
  const [stars, setStars] = useState(0);
  const [reviewCount, setReviewCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [importing, setImporting] = useState(false);

  const refresh = useCallback(async () => {
    const [installed, starCount, reviewItems] = await Promise.all([
      listInstalledCourses(),
      totalRewardStars(),
      reviewList(PROFILE),
    ]);
    setCourses(installed);
    setStars(starCount);
    setReviewCount(reviewItems.length);
    setLoading(false);
  }, []);

  useEffect(() => {
    (async () => {
      cleanupInterruptedImports();
      sweepOrphanCourseDirs();
      try {
        await ensureDemoCourse();
      } catch {
        // The bundled demo course is an engineering sample; failures do not block imported courses.
      }
      await refresh();
    })();
  }, [refresh]);

  const pickAndImport = async () => {
    if (importing) return;
    const result = await DocumentPicker.getDocumentAsync({
      type: '*/*',
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.length) return;
    const asset = result.assets[0];
    if (!asset.name?.toLowerCase().endsWith('.yuepack')) {
      Alert.alert('导入失败', '请选择 .yuepack 课程包文件');
      return;
    }
    setImporting(true);
    try {
      const importResult = await importPack(asset.uri);
      await refresh();
      Alert.alert(
        '导入成功',
        importResult.status === 'duplicate'
          ? '这个课程包之前已经导入过了，不会重复添加。'
          : `已安装课程 ${importResult.courseId}（版本 ${importResult.revision}）。`,
      );
    } catch (error) {
      Alert.alert('导入失败', error instanceof Error ? error.message : '课程包无法导入');
    } finally {
      setImporting(false);
    }
  };

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={loading || importing} onRefresh={refresh} tintColor={colors.primary} />
      }
    >
      <View style={styles.header}>
        <Text style={styles.title}>约学</Text>
        <View style={styles.starWrap}>
          <Text style={styles.star}>⭐ {stars}</Text>
        </View>
      </View>
      <Text style={styles.subtitle}>把错题变成动画片，学一学再练一练。</Text>

      {courses.length === 0 && !loading ? (
        <Card>
          <EmptyHint>还没有课程。请家长在电脑上生成课程包后，点击下方“导入课程包”安装。</EmptyHint>
        </Card>
      ) : null}

      <View style={styles.list}>
        {courses.map((installed) => (
          <Pressable
            key={installed.row.packageId}
            onPress={() => router.push({ pathname: '/lesson/[packageId]', params: { packageId: installed.row.packageId } })}
            style={({ pressed }) => [styles.courseCard, pressed && { opacity: 0.9 }]}
          >
            <Text style={styles.courseTitle} numberOfLines={2}>
              {installed.row.title}
            </Text>
            <View style={styles.badgeRow}>
              {installed.row.isDemo ? <Badge text="演示课程" kind="demo" /> : null}
              <Badge text={SUBJECT_LABEL[installed.row.subject ?? ''] ?? '课程'} />
              {installed.row.grade ? <Badge text={`${installed.row.grade} 年级`} /> : null}
              {installed.row.courseMode === 'lectureOnly' ? <Badge text="仅讲解" kind="warn" /> : null}
            </View>
            <Text style={styles.courseMeta}>
              版本 r{installed.row.revision} · {installed.manifest.assets.length} 个资源
            </Text>
          </Pressable>
        ))}
      </View>

      <View style={styles.actions}>
        <BigButton
          title={reviewCount ? `复习（${reviewCount} 项）` : '复习'}
          kind="neutral"
          onPress={() => router.push('/review')}
        />
        <BigButton title="奖励小屋" kind="neutral" onPress={() => router.push('/rewards')} />
        <BigButton title="导入课程包" onPress={pickAndImport} disabled={importing} />
        <BigButton title="家长区" kind="neutral" onPress={() => router.push('/parent')} />
      </View>
      <Text style={styles.footHint}>导入课程包不需要网络，全程在本机完成。</Text>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.bg,
  },
  content: {
    padding: 20,
    paddingTop: 64,
    paddingBottom: 40,
    gap: 16,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  title: {
    fontSize: 40,
    fontWeight: '900',
    color: colors.text,
  },
  starWrap: {
    backgroundColor: colors.card,
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
  },
  star: {
    fontSize: 18,
    fontWeight: '800',
    color: colors.star,
  },
  subtitle: {
    fontSize: 16,
    color: colors.sub,
  },
  list: {
    gap: 12,
  },
  courseCard: {
    backgroundColor: colors.card,
    borderRadius: 18,
    padding: 18,
    borderWidth: 1,
    borderColor: colors.border,
    gap: 10,
  },
  courseTitle: {
    fontSize: 19,
    fontWeight: '800',
    color: colors.text,
  },
  badgeRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  courseMeta: {
    fontSize: 13,
    color: colors.sub,
  },
  actions: {
    gap: 12,
    marginTop: 8,
  },
  footHint: {
    fontSize: 13,
    color: colors.sub,
    textAlign: 'center',
  },
});
