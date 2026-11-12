import type { PracticeItem } from '../types';

export type Submission =
  | { kind: 'numeric'; value: number }
  | { kind: 'choice'; optionId: string }
  | { kind: 'pairing'; pairs: { leftId: string; rightId: string }[] }
  | { kind: 'ordering'; order: string[] };

function samePair(a: { leftId: string; rightId: string }, b: { leftId: string; rightId: string }): boolean {
  return a.leftId === b.leftId && a.rightId === b.rightId;
}

export function gradeAnswer(practice: PracticeItem, submission: Submission): boolean {
  const answer = practice.answer;
  switch (answer.kind) {
    case 'numeric':
      return submission.kind === 'numeric' && Math.abs(submission.value - answer.value) < 1e-9;
    case 'choice':
      return submission.kind === 'choice' && submission.optionId === answer.optionId;
    case 'pairing': {
      if (submission.kind !== 'pairing') return false;
      if (submission.pairs.length !== answer.pairs.length) return false;
      const remaining = [...answer.pairs];
      for (const pair of submission.pairs) {
        const index = remaining.findIndex((candidate) => samePair(candidate, pair));
        if (index < 0) return false;
        remaining.splice(index, 1);
      }
      return true;
    }
    case 'ordering': {
      if (submission.kind !== 'ordering') return false;
      return (
        submission.order.length === answer.order.length &&
        submission.order.every((id, index) => id === answer.order[index])
      );
    }
    default:
      return false;
  }
}
