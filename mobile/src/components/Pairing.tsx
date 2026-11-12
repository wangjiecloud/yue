import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { PracticeItem } from '../types';
import type { Submission } from '../lib/grade';
import { BigButton, colors } from './ui';

export default function Pairing({
  practice,
  onSubmit,
}: {
  practice: PracticeItem;
  onSubmit: (submission: Submission) => void;
}) {
  const left = practice.left ?? [];
  const right = practice.right ?? [];
  const [selectedLeft, setSelectedLeft] = useState<string | null>(null);
  const [pairs, setPairs] = useState<{ leftId: string; rightId: string }[]>([]);
  const pairIndex = (leftId: string) => pairs.findIndex((pair) => pair.leftId === leftId);
  const rightOf = (leftId: string) => pairs.find((pair) => pair.leftId === leftId)?.rightId;
  const allPaired = pairs.length === left.length && left.length > 0;

  const submit = () => {
    if (!allPaired) return;
    onSubmit({ kind: 'pairing', pairs });
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.prompt}>{practice.prompt}</Text>
      <Text style={styles.hint}>先点左边，再点右边配对</Text>
      <View style={styles.columns}>
        <View style={styles.column}>
          {left.map((item) => {
            const index = pairIndex(item.id);
            return (
              <Pressable
                key={item.id}
                onPress={() => {
                  if (index >= 0) {
                    setPairs((current) => current.filter((pair) => pair.leftId !== item.id));
                    setSelectedLeft(null);
                  } else {
                    setSelectedLeft(item.id);
                  }
                }}
                style={[
                  styles.item,
                  selectedLeft === item.id && styles.itemSelected,
                  index >= 0 && styles.itemPaired,
                ]}
              >
                <Text style={styles.itemText}>{item.label}</Text>
                {index >= 0 ? <Text style={styles.pairBadge}>{index + 1}</Text> : null}
              </Pressable>
            );
          })}
        </View>
        <View style={styles.column}>
          {right.map((item) => {
            const pairedWith = pairs.find((pair) => pair.rightId === item.id);
            return (
              <Pressable
                key={item.id}
                onPress={() => {
                  if (!selectedLeft) return;
                  setPairs((current) => [
                    ...current.filter(
                      (pair) => pair.leftId !== selectedLeft && pair.rightId !== item.id,
                    ),
                    { leftId: selectedLeft, rightId: item.id },
                  ]);
                  setSelectedLeft(null);
                }}
                style={[styles.item, pairedWith && styles.itemPaired]}
              >
                <Text style={styles.itemText}>{item.label}</Text>
                {pairedWith ? (
                  <Text style={styles.pairBadge}>{pairIndex(pairedWith.leftId) + 1}</Text>
                ) : null}
              </Pressable>
            );
          })}
        </View>
      </View>
      <BigButton title="确认" kind="success" onPress={submit} disabled={!allPaired} />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 14,
  },
  prompt: {
    fontSize: 26,
    fontWeight: '800',
    color: colors.text,
    textAlign: 'center',
  },
  hint: {
    fontSize: 15,
    color: colors.sub,
    textAlign: 'center',
  },
  columns: {
    flexDirection: 'row',
    gap: 12,
  },
  column: {
    flex: 1,
    gap: 10,
  },
  item: {
    backgroundColor: colors.card,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 14,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  itemSelected: {
    borderColor: colors.warning,
    backgroundColor: '#FFF7E8',
  },
  itemPaired: {
    borderColor: colors.success,
  },
  itemText: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    flexShrink: 1,
  },
  pairBadge: {
    fontSize: 14,
    fontWeight: '800',
    color: '#FFFFFF',
    backgroundColor: colors.success,
    borderRadius: 999,
    width: 24,
    height: 24,
    textAlign: 'center',
    textAlignVertical: 'center',
    marginLeft: 8,
  },
});
