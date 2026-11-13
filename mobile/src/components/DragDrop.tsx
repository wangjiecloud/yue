import { useRef, useState } from 'react';
import {
  Animated,
  PanResponder,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { PracticeItem } from '../types';
import type { Submission } from '../lib/grade';
import { BigButton, colors } from './ui';

interface DropRect {
  x: number;
  y: number;
  width: number;
  height: number;
}

export default function DragDrop({
  practice,
  onSubmit,
}: {
  practice: PracticeItem;
  onSubmit: (submission: Submission) => void;
}) {
  const options = practice.options ?? [];
  const [placed, setPlaced] = useState<{ optionId: string; label: string } | null>(null);
  const dropRectRef = useRef<DropRect | null>(null);
  const panRefs = useRef(new Map<string, Animated.ValueXY>()).current;

  const panFor = (optionId: string) => {
    let pan = panRefs.get(optionId);
    if (!pan) {
      pan = new Animated.ValueXY();
      panRefs.set(optionId, pan);
    }
    return pan;
  };

  const panResponders = useRef(
    new Map<string, ReturnType<typeof PanResponder.create>>(),
  ).current;

  const responderFor = (optionId: string, label: string) => {
    let responder = panResponders.get(optionId);
    if (!responder) {
      const pan = panFor(optionId);
      responder = PanResponder.create({
        onStartShouldSetPanResponder: () => true,
        onMoveShouldSetPanResponder: () => true,
        onPanResponderGrant: () => {
          pan.setOffset({
            x: (pan.x as unknown as { _value: number })._value,
            y: (pan.y as unknown as { _value: number })._value,
          });
          pan.setValue({ x: 0, y: 0 });
        },
        onPanResponderMove: Animated.event([null, { dx: pan.x, dy: pan.y }], {
          useNativeDriver: false,
        }),
        onPanResponderRelease: (_event, gesture) => {
          pan.flattenOffset();
          const rect = dropRectRef.current;
          const inside =
            rect !== null &&
            gesture.moveX >= rect.x &&
            gesture.moveX <= rect.x + rect.width &&
            gesture.moveY >= rect.y - 20 &&
            gesture.moveY <= rect.y + rect.height + 20;
          if (inside) {
            setPlaced({ optionId, label });
          }
          Animated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
        },
        onPanResponderTerminate: () => {
          Animated.spring(pan, { toValue: { x: 0, y: 0 }, useNativeDriver: false }).start();
        },
      });
      panResponders.set(optionId, responder);
    }
    return responder;
  };

  const submit = () => {
    if (!placed) return;
    if (practice.answer.kind === 'numeric') {
      const value = Number.parseFloat(placed.label);
      if (Number.isFinite(value)) {
        onSubmit({ kind: 'numeric', value });
      }
    } else if (practice.answer.kind === 'choice') {
      onSubmit({ kind: 'choice', optionId: placed.optionId });
    }
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.prompt}>{practice.prompt}</Text>
      <View
        style={styles.dropZone}
        onLayout={(event) => {
          const { width, height } = event.nativeEvent.layout;
          dropRectRef.current = { x: -1, y: -1, width, height };
        }}
        ref={(node) => {
          if (node) {
            node.measure((x, y, width, height, pageX, pageY) => {
              dropRectRef.current = { x: pageX, y: pageY, width, height };
            });
          }
        }}
      >
        <Text style={styles.dropHint}>把正确答案拖进这个框</Text>
        {placed ? <Text style={styles.placedText}>{placed.label}</Text> : null}
      </View>
      <View style={styles.chipRow}>
        {options.map((option) => (
          <Animated.View
            key={option.id}
            style={[styles.chip, { transform: panFor(option.id).getTranslateTransform() }]}
            {...responderFor(option.id, option.label).panHandlers}
          >
            <Text style={styles.chipText}>{option.label}</Text>
          </Animated.View>
        ))}
      </View>
      <View style={styles.tapRow}>
        <Text style={styles.tapHint}>不方便拖动？直接点选：</Text>
        {options.map((option) => (
          <Pressable
            key={`tap-${option.id}`}
            onPress={() => setPlaced({ optionId: option.id, label: option.label })}
            style={[styles.tapChip, placed?.optionId === option.id && styles.tapChipActive]}
          >
            <Text style={styles.tapChipText}>{option.label}</Text>
          </Pressable>
        ))}
      </View>
      <Pressable onPress={() => setPlaced(null)} style={styles.resetWrap}>
        <Text style={styles.resetText}>放错了？点这里重放</Text>
      </Pressable>
      <BigButton title="确认" kind="success" onPress={submit} disabled={!placed} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 16,
  },
  prompt: {
    fontSize: 30,
    fontWeight: '800',
    color: colors.text,
    textAlign: 'center',
  },
  dropZone: {
    borderWidth: 3,
    borderStyle: 'dashed',
    borderColor: colors.primary,
    borderRadius: 20,
    backgroundColor: '#F2F6FF',
    minHeight: 120,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
  },
  dropHint: {
    fontSize: 15,
    color: colors.sub,
  },
  placedText: {
    fontSize: 40,
    fontWeight: '900',
    color: colors.primaryDark,
  },
  chipRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 14,
  },
  chip: {
    backgroundColor: colors.card,
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: 18,
    minWidth: 96,
    minHeight: 64,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
    elevation: 3,
  },
  chipText: {
    fontSize: 24,
    fontWeight: '800',
    color: colors.primaryDark,
  },
  tapRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
  },
  tapHint: {
    fontSize: 14,
    color: colors.sub,
  },
  tapChip: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 999,
    paddingVertical: 8,
    paddingHorizontal: 14,
    backgroundColor: colors.card,
    minHeight: 40,
    justifyContent: 'center',
  },
  tapChipActive: {
    borderColor: colors.primary,
    backgroundColor: colors.chip,
  },
  tapChipText: {
    fontSize: 16,
    fontWeight: '700',
    color: colors.primaryDark,
  },
  resetWrap: {
    alignItems: 'center',
  },
  resetText: {
    fontSize: 14,
    color: colors.sub,
    textDecorationLine: 'underline',
  },
});
