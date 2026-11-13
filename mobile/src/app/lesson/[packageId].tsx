import { useCallback, useEffect, useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, View } from 'react-native';
import { useEventListener } from 'expo';
import { router, useLocalSearchParams } from 'expo-router';
import { useVideoPlayer, VideoView, type VideoPlayer } from 'expo-video';

import DragDrop from '../../components/DragDrop';
import Ordering from '../../components/Ordering';
import Pairing from '../../components/Pairing';
import SingleChoice from '../../components/SingleChoice';
import { BigButton, colors } from '../../components/ui';
import type { ChapterTime } from '../../types';
import { assetUri, loadInstalledCourse, type InstalledCourse } from '../../lib/pack';
import { LessonRuntime, type LessonEvent, type Phase } from '../../lib/engine';
import type { Submission } from '../../lib/grade';
import * as db from '../../lib/db';
import { ensureAudioMode, playOnce, type PlayOnceHandle } from '../../lib/audio';
import { nowIso } from '../../lib/util';

const PROFILE = 'default';

function ChapterBar({
  chapters,
  player,
}: {
  chapters: ChapterTime[];
  player: VideoPlayer;
}) {
  if (!chapters.length) return null;
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.chapterScroll}>
      {chapters.map((chapter) => (
        <BigButton
          key={chapter.chapterId}
          title={chapter.title}
          kind="neutral"
          onPress={() => {
            player.currentTime = chapter.startMs / 1000;
            player.play();
          }}
        />
      ))}
    </ScrollView>
  );
}

function VideoStage({
  uri,
  chapters,
  onEnded,
  onSkip,
}: {
  uri: string;
  chapters: ChapterTime[];
  onEnded: () => void;
  onSkip: () => void;
}) {
  const player = useVideoPlayer(uri, (instance) => {
    instance.loop = false;
  });
  useEventListener(player, 'playToEnd', onEnded);
  useEffect(() => {
    player.play();
  }, [player]);
  return (
    <View style={styles.videoWrap}>
      <VideoView
        player={player}
        contentFit="contain"
        nativeControls
        style={styles.video}
        allowsPictureInPicture={false}
      />
      <ChapterBar chapters={chapters} player={player} />
      <BigButton title="跳过动画片，开始练习" kind="neutral" onPress={onSkip} />
    </View>
  );
}

function MessageStage({
  text,
  result,
  audioUri,
  onContinue,
}: {
  text: string;
  result: 'correct' | 'incorrect' | 'assisted' | null;
  audioUri: string | null;
  onContinue: () => void;
}) {
  const audioRef = useRef<PlayOnceHandle | null>(null);
  useEffect(() => {
    if (!audioUri) return;
    audioRef.current = playOnce(audioUri, () => undefined);
    return () => {
      audioRef.current?.stop();
      audioRef.current = null;
    };
  }, [audioUri]);
  const backgroundColor =
    result === 'correct' ? '#EAF7EF' : result === 'assisted' ? '#FFF7E8' : '#F2F6FF';
  const borderColor =
    result === 'correct' ? colors.success : result === 'assisted' ? colors.warning : colors.primary;
  return (
    <View style={[styles.messageCard, { backgroundColor, borderColor }]}>
      <Text style={styles.messageText}>{text}</Text>
      <BigButton title="继续" kind="success" onPress={onContinue} />
    </View>
  );
}

export default function LessonScreen() {
  const { packageId } = useLocalSearchParams<{ packageId: string }>();
  const [installed, setInstalled] = useState<InstalledCourse | null>(null);
  const [phase, setPhase] = useState<Phase | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [practiceDone, setPracticeDone] = useState<string[]>([]);
  const [starBurst, setStarBurst] = useState(0);
  const runtimeRef = useRef<LessonRuntime | null>(null);
  const installedRef = useRef<InstalledCourse | null>(null);
  const practiceDoneRef = useRef<string[]>([]);
  const videoWatchedRef = useRef(false);

  const handleEvent = useCallback(async (event: LessonEvent) => {
    const current = installedRef.current;
    if (!current) return;
    const lesson = current.course.lessons[0];
    if (event.type === 'practiceConcluded') {
      const practice = current.course.practices.find(
        (candidate) => candidate.practiceId === event.practiceId,
      );
      await db.recordAttempt({
        profileId: PROFILE,
        packageId: current.row.packageId,
        courseId: current.course.courseId,
        questionId: lesson.questionId,
        questionRevision: lesson.questionRevision,
        practiceId: event.practiceId,
        practiceKind: event.practiceKind,
        firstAnswerCorrect: event.firstAnswerCorrect ? 1 : 0,
        attemptCount: event.attemptCount,
        hintsUsed: event.hintsUsed,
        result: event.result,
        knowledgePoints: practice?.knowledgePoints ?? [],
        createdAt: nowIso(),
      });
      practiceDoneRef.current = [
        ...new Set([...practiceDoneRef.current, event.practiceId]),
      ];
      setPracticeDone(practiceDoneRef.current);
      await db.saveLessonProgress(PROFILE, current.row.packageId, lesson.lessonId, {
        videoWatched: true,
        completedPracticeIds: practiceDoneRef.current,
      });
    } else if (event.type === 'reward') {
      const granted = await db.grantReward(PROFILE, event.dedupKey, event.amount, '课程学习');
      if (granted) {
        setStarBurst((count) => count + 1);
      }
    } else if (event.type === 'completed') {
      await db.recordCompletion(
        PROFILE,
        current.row.packageId,
        lesson.lessonId,
        current.course.courseId,
        current.course.revision,
        0,
      );
    }
  }, []);

  useEffect(() => {
    let disposed = false;
    (async () => {
      await ensureAudioMode();
      const current = await loadInstalledCourse(packageId);
      const lesson = current.course.lessons[0];
      const progress = await db.loadLessonProgress(PROFILE, packageId, lesson.lessonId);
      const runtime = new LessonRuntime(current.course, lesson, (event) => {
        void handleEvent(event);
      });
      practiceDoneRef.current = progress.completedPracticeIds;
      videoWatchedRef.current = progress.videoWatched;
      setPracticeDone(progress.completedPracticeIds);
      runtime.start(progress.videoWatched, progress.completedPracticeIds);
      if (disposed) return;
      runtimeRef.current = runtime;
      installedRef.current = current;
      setInstalled(current);
      setPhase({ ...runtime.phase });
    })().catch((cause: unknown) => {
      setError(cause instanceof Error ? cause.message : '课程加载失败');
    });
    return () => {
      disposed = true;
    };
  }, [packageId, handleEvent]);

  useEffect(() => {
    const timer = setInterval(() => {
      void db.addActiveTime(PROFILE, 30_000);
    }, 30_000);
    return () => clearInterval(timer);
  }, []);

  useEffect(() => {
    if (starBurst === 0) return;
    const timer = setTimeout(() => setStarBurst(0), 1600);
    return () => clearTimeout(timer);
  }, [starBurst]);

  const syncPhase = () => {
    const runtime = runtimeRef.current;
    if (runtime) {
      setPhase({ ...runtime.phase });
    }
  };

  const onVideoEnded = async () => {
    const current = installedRef.current;
    const runtime = runtimeRef.current;
    if (!current || !runtime) return;
    const lesson = current.course.lessons[0];
    videoWatchedRef.current = true;
    await db.saveLessonProgress(PROFILE, current.row.packageId, lesson.lessonId, {
      videoWatched: true,
      completedPracticeIds: practiceDoneRef.current,
    });
    runtime.onVideoEnded();
    syncPhase();
  };

  const onSkipVideo = async () => {
    const current = installedRef.current;
    const runtime = runtimeRef.current;
    if (!current || !runtime) return;
    const lesson = current.course.lessons[0];
    // Skipping is allowed so the child can practise, but it must not be
    // recorded as having watched the whole explanation (A11).
    await db.saveLessonProgress(PROFILE, current.row.packageId, lesson.lessonId, {
      videoWatched: videoWatchedRef.current,
      completedPracticeIds: practiceDoneRef.current,
    });
    runtime.skipVideo();
    syncPhase();
  };

  const onSubmit = (submission: Submission) => {
    const runtime = runtimeRef.current;
    if (!runtime) return;
    runtime.submitAnswer(submission);
    syncPhase();
  };

  const restartLesson = () => {
    const current = installedRef.current;
    if (!current) return;
    const lesson = current.course.lessons[0];
    const runtime = new LessonRuntime(current.course, lesson, (event) => {
      void handleEvent(event);
    });
    runtimeRef.current = runtime;
    practiceDoneRef.current = [];
    videoWatchedRef.current = false;
    setPracticeDone([]);
    runtime.start(false, []);
    syncPhase();
  };

  const audioUriFor = (assetId: string): string | null => {
    const current = installedRef.current;
    if (!current) return null;
    try {
      return assetUri(current, assetId);
    } catch {
      return null;
    }
  };

  if (error) {
    return (
      <View style={styles.screen}>
        <Text style={styles.errorText}>{error}</Text>
        <BigButton title="返回" kind="neutral" onPress={() => router.back()} />
      </View>
    );
  }

  if (!installed || !phase) {
    return (
      <View style={styles.screen}>
        <Text style={styles.loadingText}>正在打开课程…</Text>
      </View>
    );
  }

  const lesson = installed.course.lessons[0];

  return (
    <View style={styles.screen}>
      <View style={styles.progressRow}>
        {lesson.practiceIds.map((practiceId) => (
          <View
            key={practiceId}
            style={[styles.dot, practiceDone.includes(practiceId) && styles.dotDone]}
          />
        ))}
      </View>
      <ScrollView contentContainerStyle={styles.body}>
        {phase.kind === 'video' ? (
          <VideoStage
            uri={assetUri(installed, lesson.videoAssetId)}
            chapters={lesson.chapters}
            onEnded={() => {
              void onVideoEnded();
            }}
            onSkip={() => {
              void onSkipVideo();
            }}
          />
        ) : null}
        {phase.kind === 'interaction' ? (
          <View style={styles.practiceWrap}>
            <Text style={styles.attemptHint}>
              第 {phase.attempts + 1} 次作答，最多 {phase.practice.maxAttempts} 次
            </Text>
            {phase.practice.kind === 'singleChoice' ? (
              <SingleChoice practice={phase.practice} onSubmit={onSubmit} />
            ) : null}
            {phase.practice.kind === 'dragDrop' ? (
              <DragDrop practice={phase.practice} onSubmit={onSubmit} />
            ) : null}
            {phase.practice.kind === 'pairing' ? (
              <Pairing practice={phase.practice} onSubmit={onSubmit} />
            ) : null}
            {phase.practice.kind === 'ordering' ? (
              <Ordering practice={phase.practice} onSubmit={onSubmit} />
            ) : null}
          </View>
        ) : null}
        {phase.kind === 'message' ? (
          <MessageStage
            text={phase.text}
            result={phase.result}
            audioUri={phase.audioAssetId ? audioUriFor(phase.audioAssetId) : null}
            onContinue={() => {
              runtimeRef.current?.continueFromMessage();
              syncPhase();
            }}
          />
        ) : null}
        {phase.kind === 'finished' ? (
          <View style={styles.finishedWrap}>
            <Text style={styles.finishedTitle}>完成啦！🎉</Text>
            <Text style={styles.finishedText}>这一课学完了，奖励已经记录到你的星星里。</Text>
            <View style={styles.finishedActions}>
              <BigButton title="再学一遍" kind="neutral" onPress={restartLesson} />
              <BigButton title="回主页" kind="success" onPress={() => router.back()} />
            </View>
          </View>
        ) : null}
      </ScrollView>
      {starBurst > 0 ? (
        <View style={styles.starBurst} pointerEvents="none">
          <Text style={styles.starBurstText}>⭐ +{starBurst}</Text>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: colors.bg,
    padding: 16,
    gap: 12,
  },
  progressRow: {
    flexDirection: 'row',
    gap: 8,
    justifyContent: 'center',
  },
  dot: {
    width: 14,
    height: 14,
    borderRadius: 999,
    backgroundColor: colors.border,
  },
  dotDone: {
    backgroundColor: colors.success,
  },
  body: {
    gap: 16,
    paddingBottom: 32,
  },
  videoWrap: {
    gap: 12,
  },
  video: {
    width: '100%',
    aspectRatio: 16 / 9,
    backgroundColor: '#101820',
    borderRadius: 16,
  },
  chapterScroll: {
    flexDirection: 'row',
  },
  practiceWrap: {
    gap: 16,
    paddingTop: 8,
  },
  attemptHint: {
    fontSize: 14,
    color: colors.sub,
    textAlign: 'center',
  },
  messageCard: {
    borderRadius: 18,
    borderWidth: 2,
    padding: 22,
    gap: 18,
  },
  messageText: {
    fontSize: 24,
    fontWeight: '800',
    color: colors.text,
    lineHeight: 36,
    textAlign: 'center',
  },
  finishedWrap: {
    alignItems: 'center',
    gap: 14,
    paddingTop: 24,
  },
  finishedTitle: {
    fontSize: 32,
    fontWeight: '900',
    color: colors.text,
  },
  finishedText: {
    fontSize: 17,
    color: colors.sub,
    textAlign: 'center',
    lineHeight: 26,
  },
  finishedActions: {
    flexDirection: 'row',
    gap: 12,
    marginTop: 8,
  },
  starBurst: {
    position: 'absolute',
    top: 80,
    alignSelf: 'center',
    backgroundColor: colors.card,
    borderRadius: 999,
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderWidth: 1,
    borderColor: colors.star,
    elevation: 6,
  },
  starBurstText: {
    fontSize: 22,
    fontWeight: '900',
    color: colors.star,
  },
  errorText: {
    fontSize: 17,
    color: colors.danger,
    textAlign: 'center',
    lineHeight: 26,
  },
  loadingText: {
    fontSize: 17,
    color: colors.sub,
    textAlign: 'center',
  },
});
