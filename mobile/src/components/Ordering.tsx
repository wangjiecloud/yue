import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { PracticeItem } from '../types';
import type { Submission } from '../lib/grade';
import { BigButton, colors } from './ui';

export default function Ordering({
  practice,
  onSubmit,
}: {
  practice: PracticeItem;
  onSubmit: (submission: Submission) => void;
}) {
  const options = practice.options ?? [];
  const [order, setOrder] = useState<string[]>([]);
  const positionOf = (optionId: string) => order.indexOf(optionId);
  const allOrdered = order.length === options.length && options.length > 0;

  const submit = () => {
    if (!allOrdered) return;
    onSubmit({ kind: 'ordering', order });
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.prompt}>{practice.prompt}</Text>
      <Text style={styles.hint}>按正确顺序依次点击</Text>
      <View style={styles.options}>
        {options.map((option) => {
          const index = positionOf(option.id);
          return (
            <Pressable
              key={option.id}
              onPress={() => {
                setOrder((current) =>
                  index >= 0
                    ? current.filter((id) => id !== option.id)
                    : [...current, option.id],
                );
              }}
              style={[styles.option, index >= 0 && styles.optionPicked]}
            >
              <Text style={styles.optionText}>{option.label}</Text>
              {index >= 0 ? <Text style={styles.orderBadge}>{index + 1}</Text> : null}
            </Pressable>
          );
        })}
      </View>
      <BigButton title="确认" kind="success" onPress={submit} disabled={!allOrdered} />
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
  options: {
    gap: 10,
  },
  option: {
    backgroundColor: colors.card,
    borderWidth: 2,
    borderColor: colors.border,
    borderRadius: 14,
    paddingVertical: 14,
    paddingHorizontal: 16,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  optionPicked: {
    borderColor: colors.primary,
    backgroundColor: '#F2F6FF',
  },
  optionText: {
    fontSize: 18,
    fontWeight: '700',
    color: colors.text,
    flexShrink: 1,
  },
  orderBadge: {
    fontSize: 14,
    fontWeight: '800',
    color: '#FFFFFF',
    backgroundColor: colors.primary,
    borderRadius: 999,
    width: 24,
    height: 24,
    textAlign: 'center',
    textAlignVertical: 'center',
    marginLeft: 8,
  },
});
