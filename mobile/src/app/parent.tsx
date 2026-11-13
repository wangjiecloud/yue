import { useCallback, useEffect, useState } from 'react';
import {
  Alert,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import * as DocumentPicker from 'expo-document-picker';

import { BigButton, Card, colors, EmptyHint, SectionTitle } from '../components/ui';
import { exportBackup, restoreBackup, shareBackup } from '../lib/backup';
import * as db from '../lib/db';
import { listInstalledCourses, uninstallCourse, type InstalledCourse } from '../lib/pack';

const PROFILE = 'default';

export default function ParentScreen() {
  const [unlocked, setUnlocked] = useState(false);
  const [pinReady, setPinReady] = useState(false);
  const [hasPinSet, setHasPinSet] = useState(false);
  const [pin, setPin] = useState('');
  const [pinError, setPinError] = useState('');
  const [courses, setCourses] = useState<InstalledCourse[]>([]);
  const [completions, setCompletions] = useState(0);
  const [summary, setSummary] = useState<db.AttemptSummary | null>(null);
  const [review, setReview] = useState<
    { packageId: string; practiceId: string; reason: string; priority: number; updatedAt: string }[]
  >([]);
  const [active, setActive] = useState<{ day: string; ms: number }[]>([]);
  const [refreshing, setRefreshing] = useState(false);

  const refresh = useCallback(async () => {
    const [installed, completionCount, attemptStats, reviewItems, activeTime] = await Promise.all([
      listInstalledCourses(),
      db.countCompletions(PROFILE),
      db.attemptSummary(PROFILE),
      db.reviewList(PROFILE),
      db.recentActiveTime(PROFILE, 7),
    ]);
    setCourses(installed);
    setCompletions(completionCount);
    setSummary(attemptStats);
    setReview(reviewItems);
    setActive(activeTime);
    setRefreshing(false);
  }, []);

  useEffect(() => {
    (async () => {
      const existing = await db.hasPin();
      setHasPinSet(existing);
      setPinReady(true);
      if (!existing) setUnlocked(true);
      await refresh();
    })();
  }, [refresh]);

  const submitPin = async () => {
    setPinError('');
    if (!hasPinSet) {
      if (pin.length < 4) {
        setPinError('家长 PIN 至少 4 位。');
        return;
      }
      await db.setPin(pin);
      setHasPinSet(true);
      setUnlocked(true);
      setPin('');
      return;
    }
    if (await db.verifyPin(pin)) {
      setUnlocked(true);
      setPin('');
    } else {
      setPinError('PIN 不正确。');
    }
  };

  const onExportBackup = async () => {
    try {
      const file = await exportBackup();
      await shareBackup(file);
      Alert.alert('已导出', '备份文件包含学习记录，但不含原始题图和课程视频。');
    } catch (error) {
      Alert.alert('导出失败', error instanceof Error ? error.message : '无法导出备份');
    }
  };

  const onRestoreBackup = async () => {
    const result = await DocumentPicker.getDocumentAsync({
      type: 'application/json',
      copyToCacheDirectory: true,
    });
    if (result.canceled || !result.assets?.length) return;
    try {
      const restored = await restoreBackup(result.assets[0].uri);
      await refresh();
      Alert.alert(
        '恢复完成',
        restored.restored ? `已恢复 ${restored.items} 条记录。` : '这份备份之前已经恢复过。',
      );
    } catch (error) {
      Alert.alert('恢复失败', error instanceof Error ? error.message : '备份无法恢复');
    }
  };

  const onDeleteCourse = (course: InstalledCourse) => {
    Alert.alert('删除课程', `确定删除《${course.row.title}》吗？`, [
      { text: '取消', style: 'cancel' },
      {
        text: '保留学习记录',
        onPress: async () => {
          await uninstallCourse(course.row.packageId, false);
          await refresh();
        },
      },
      {
        text: '同时删除记录',
        style: 'destructive',
        onPress: async () => {
          await uninstallCourse(course.row.packageId, true);
          await refresh();
        },
      },
    ]);
  };

  const onChangePin = () => {
    Alert.alert('修改家长 PIN', '当前版本会清除旧 PIN，请重新设置。', [
      { text: '取消', style: 'cancel' },
      {
        text: '清除并重设',
        style: 'destructive',
        onPress: async () => {
          await db.clearPin();
          setHasPinSet(false);
          setPin('');
        },
      },
    ]);
  };

  if (!pinReady) {
    return (
      <View style={styles.screen}>
        <Text style={styles.muted}>正在打开家长区…</Text>
      </View>
    );
  }

  if (!unlocked) {
    return (
      <View style={styles.screen}>
        <Card style={styles.pinCard}>
          <SectionTitle>家长 PIN</SectionTitle>
          <Text style={styles.muted}>输入 4 位以上 PIN 进入家长区，防止孩子误删课程。</Text>
          <TextInput
            value={pin}
            onChangeText={setPin}
            keyboardType="number-pad"
            secureTextEntry
            placeholder="请输入 PIN"
            style={styles.input}
            onSubmitEditing={submitPin}
          />
          {pinError ? <Text style={styles.error}>{pinError}</Text> : null}
          <BigButton title="进入家长区" onPress={submitPin} />
        </Card>
      </View>
    );
  }

  return (
    <ScrollView
      style={styles.screen}
      contentContainerStyle={styles.content}
      refreshControl={
        <RefreshControl refreshing={refreshing} onRefresh={() => { setRefreshing(true); void refresh(); }} />
      }
    >
      <Card>
        <SectionTitle>学习报告</SectionTitle>
        <Text style={styles.reportLine}>完成课时：{completions}</Text>
        <Text style={styles.reportLine}>
          练习 {summary?.total ?? 0} 次 · 独立答对 {summary?.independent ?? 0} 次 · 提示后完成{' '}
          {summary?.assisted ?? 0} 次
        </Text>
        <Text style={styles.reportLine}>待复习练习：{review.length} 项</Text>
        <Text style={styles.muted}>
          近 7 天有效学习：
          {active.length
            ? active.map((item) => `${item.day.slice(5)} ${Math.round(item.ms / 60000)} 分钟`).join('，')
            : '暂无记录'}
        </Text>
      </Card>

      <Card>
        <SectionTitle>待复习</SectionTitle>
        {review.length ? (
          review.slice(0, 10).map((item) => (
            <Text key={`${item.packageId}:${item.practiceId}`} style={styles.reportLine}>
              {item.reason}（{item.packageId} / {item.practiceId}）
            </Text>
          ))
        ) : (
          <EmptyHint>目前没有需要重点复习的练习。</EmptyHint>
        )}
      </Card>

      <Card>
        <SectionTitle>已安装课程</SectionTitle>
        {courses.length ? (
          courses.map((course) => (
            <View key={course.row.packageId} style={styles.courseRow}>
              <View style={styles.courseInfo}>
                <Text style={styles.courseTitle}>{course.row.title}</Text>
                <Text style={styles.muted}>
                  {course.row.subject ?? '课程'} · r{course.row.revision}
                  {course.row.isDemo ? ' · 演示课程' : ''}
                </Text>
              </View>
              <BigButton
                title="删除"
                kind="danger"
                onPress={() => onDeleteCourse(course)}
              />
            </View>
          ))
        ) : (
          <EmptyHint>还没有安装课程。</EmptyHint>
        )}
      </Card>

      <Card>
        <SectionTitle>备份与恢复</SectionTitle>
        <Text style={styles.muted}>
          备份默认不含原始题图、角色素材和课程视频；卸载 App 或清除数据会丢失私有目录中的课程与记录。
        </Text>
        <View style={styles.actions}>
          <BigButton title="导出学习备份" onPress={onExportBackup} />
          <BigButton title="从备份恢复" kind="neutral" onPress={onRestoreBackup} />
        </View>
      </Card>

      <Card>
        <SectionTitle>家长 PIN</SectionTitle>
        <Text style={styles.muted}>
          {hasPinSet ? '已设置 PIN，可清除后重新设置。' : '当前未设置 PIN，建议设置一个。'}
        </Text>
        <View style={styles.actions}>
          <BigButton title={hasPinSet ? '重设 PIN' : '设置 PIN'} kind="neutral" onPress={onChangePin} />
        </View>
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
  pinCard: {
    margin: 16,
    gap: 12,
  },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 12,
    fontSize: 18,
    backgroundColor: colors.card,
  },
  muted: {
    fontSize: 14,
    color: colors.sub,
    lineHeight: 21,
  },
  error: {
    color: colors.danger,
    fontSize: 14,
  },
  reportLine: {
    fontSize: 15,
    color: colors.text,
    marginBottom: 6,
    lineHeight: 22,
  },
  courseRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: 12,
    paddingVertical: 8,
  },
  courseInfo: {
    flex: 1,
    gap: 4,
  },
  courseTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.text,
  },
  actions: {
    gap: 10,
    marginTop: 10,
  },
});
