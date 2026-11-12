import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { PracticeItem } from '../types';
import type { Submission } from '../lib/grade';
import { colors } from './ui';

export default function SingleChoice({
  practice,
  onSubmit,
}: {
  practice: PracticeItem;
  onSubmit: (submission: Submission) => void;
}) {
  const [selected, setSelected] = useState<string | null>(null);
  const options = practice.options ?? [];
  return (
    <View style={styles.wrap}>
      <Text style={styles.prompt}>{practice.prompt}</Text>
      <View style={styles.options}>
        {options.map((option) => (
          <Pressable
            key={option.id}
            onPress={() => {
              setSelected(option.id);
              onSubmit({ kind: 'choice', optionId: option.id });
            }}
            style={({ pressed }) => [
              styles.option,
              selected === option.id && styles.optionSelected,
              pressed && styles.optionPressed,
            ]}
          >
            <Text
              style={[styles.optionText, selected === option.id && styles.optionTextSelected]}
            >
              {option.label}
            </Text>
          </Pressable>
        ))}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    gap: 18,
  },
  prompt: {
    fontSize: 30,
    fontWeight: '800',
    color: colors.text,
    textAlign: 'center',
  },
  options: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    justifyContent: 'center',
    gap: 14,
  },
  option: {
    backgroundColor: colors.card,
    borderWidth: 2,
    borderColor: colors.primary,
    borderRadius: 20,
    minWidth: 120,
    minHeight: 72,
    paddingHorizontal: 26,
    alignItems: 'center',
    justifyContent: 'center',
  },
  optionSelected: {
    backgroundColor: colors.primary,
  },
  optionPressed: {
    transform: [{ scale: 0.96 }],
  },
  optionText: {
    fontSize: 26,
    fontWeight: '800',
    color: colors.primaryDark,
  },
  optionTextSelected: {
    color: '#FFFFFF',
  },
});
