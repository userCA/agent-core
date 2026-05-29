import { useRef } from 'react';

interface RecorderState {
  recording: boolean;
  audioUrl: string | null;
  base64: string | null;
  error: string | null;
}

export function useAudioRecorder(onResult: (base64: string, blob: Blob) => void) {
  const mediaRecorder = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const stream = useRef<MediaStream | null>(null);
  const stateRef = useRef<RecorderState>({
    recording: false,
    audioUrl: null,
    base64: null,
    error: null,
  });

  const start = async () => {
    try {
      stream.current = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mr = new MediaRecorder(stream.current);
      mediaRecorder.current = mr;
      chunks.current = [];

      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunks.current.push(e.data);
      };

      mr.onstop = async () => {
        const blob = new Blob(chunks.current, { type: 'audio/webm' });
        const url = URL.createObjectURL(blob);
        const base64 = await blobToBase64(blob);
        stateRef.current = {
          recording: false,
          audioUrl: url,
          base64,
          error: null,
        };
        onResult(base64, blob);
        // release mic
        stream.current?.getTracks().forEach((t) => t.stop());
        stream.current = null;
      };

      mr.start();
      stateRef.current = { recording: true, audioUrl: null, base64: null, error: null };
    } catch (err) {
      stateRef.current = {
        recording: false,
        audioUrl: null,
        base64: null,
        error: err instanceof Error ? err.message : 'Microphone access denied',
      };
    }
  };

  const stop = () => {
    if (mediaRecorder.current && mediaRecorder.current.state === 'recording') {
      mediaRecorder.current.stop();
    }
  };

  return { start, stop, stateRef };
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}
