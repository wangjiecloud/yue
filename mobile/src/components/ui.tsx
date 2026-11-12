import { Pressable, StyleSheet, Text, View } from 'react-native';
import type { ReactNode } from 'react';

export const colors = {
  primary: '#3B6FE0',
  primaryDark: '#2C56B4',
  bg: '#F7F9FC',
  card: '#FFFFFF',
  success: '#2E9E5B',
  danger: '#D64545',
  warning: '#E8A33D',
  star: '#F5A623',
  text: '#22303F',
  sub: '#66788C',
  chip: '#EAF1FD',
  chipText: '#2C56B4',
  border: '#D9E2EC',
};

export function BigButton({
  title,
  onPress,
  kind = 'primary',
  disabled = false,
}: {
  title: string;
  onPress: () => void;
  kind?: 'primary' | 'success' | 'neutral' | 'danger';
  disabled?: boolean;
}) {
  const background =
    kind === 'success'
      ? colors.success
      : kind === 'danger'
        ? colors.danger
        : kind === 'neutral'
          ? colors.chip
          : colors.primary;
  const textColor = kind === 'neutral' ? colors.chipText : '#FFFFFF';
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: disabled ? '#B9C4D0' : background, opacity: pressed ? 0.85 : 1 },
      ]}
    >
      <Text style={[styles.buttonText, { color: textColor }]}>{title}</Text>
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Badge({ text, kind = 'info' }: { text: string; kind?: 'info' | 'warn' | 'demo' }) {
  const backgroundColor =
    kind === 'warn' ? '#FDF3E1' : kind === 'demo' ? '#EFE9FB' : colors.chip;
  const color = kind === 'warn' ? '#9A6A12' : kind === 'demo' ? '#6B4FA8' : colors.chipText;
  return (
    <View style={[styles.badge, { backgroundColor }]}>
      <Text style={[styles.badgeText, { color }]}>{text}</Text>
    </View>
  );
}

export function SectionTitle({ children }: { children: ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

export function EmptyHint({ children }: { children: ReactNode }) {
  return <Text style={styles.emptyHint}>{children}</Text>;
}

const styles = StyleSheet.create({
  button: {
    borderRadius: 16,
    paddingVertical: 14,
    paddingHorizontal: 20,
    alignItems: 'center',
    justifyContent: 'center',
    minHeight: 52,
  },
  buttonText: {
    fontSize: 18,
    fontWeight: '700',
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: 16,
    padding: 16,
    borderWidth: 1,
    borderColor: colors.border,
  },
  badge: {
    borderRadius: 999,
    paddingVertical: 4,
    paddingHorizontal: 10,
    alignSelf: 'flex-start',
  },
  badgeText: {
    fontSize: 12,
    fontWeight: '600',
  },
  sectionTitle: {
    fontSize: 17,
    fontWeight: '700',
    color: colors.text,
    marginBottom: 8,
  },
  emptyHint: {
    fontSize: 15,
    color: colors.sub,
    lineHeight: 22,
  },
});
