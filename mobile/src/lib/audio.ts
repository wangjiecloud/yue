import { createAudioPlayer, setAudioModeAsync, type AudioPlayer } from 'expo-audio';

let audioModeConfigured = false;

export async function ensureAudioMode(): Promise<void> {
  if (audioModeConfigured) return;
  try {
    await setAudioModeAsync({
      playsInSilentMode: true,
      interruptionMode: 'mixWithOthers',
      shouldPlayInBackground: false,
    });
    audioModeConfigured = true;
  } catch {
    // Audio mode setup is best effort; playback still works with defaults.
  }
}

export interface PlayOnceHandle {
  stop(): void;
}

export function playOnce(uri: string, onEnded: () => void): PlayOnceHandle {
  let ended = false;
  let player: AudioPlayer;
  try {
    player = createAudioPlayer({ uri });
  } catch {
    onEnded();
    return { stop: () => undefined };
  }
  const finish = () => {
    if (ended) return;
    ended = true;
    try {
      player.remove();
    } catch {
      // best effort release
    }
    onEnded();
  };
  const subscription = player.addListener('playbackStatusUpdate', (status) => {
    if (status.didJustFinish || status.error) {
      subscription.remove();
      finish();
    }
  });
  try {
    player.play();
  } catch {
    finish();
  }
  return {
    stop: () => {
      try {
        player.pause();
      } catch {
        // best effort
      }
      finish();
    },
  };
}
