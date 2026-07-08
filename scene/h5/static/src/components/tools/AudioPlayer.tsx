import React from 'react';
import type { AudioDisplay } from '../../api/types';

interface Props {
  audio: AudioDisplay;
}

export default function AudioPlayer({ audio }: Props) {
  return (
    <div className="audio-container" style={{ margin: '12px 0' }}>
      <div
        className="audio-header"
        style={{ fontSize: 12, color: 'var(--mute)', marginBottom: 8, fontFamily: 'var(--font-mono)' }}
      >
        [audio] {audio.prompt || 'generated music'}
      </div>
      {audio.urls.map((url, i) => (
        <div key={i} style={{ marginBottom: 8 }}>
          <span style={{ fontSize: 11, color: 'var(--ash)', fontFamily: 'var(--font-mono)' }}>
            #{i + 1}
          </span>
          <audio controls src={url} style={{ width: '100%', marginTop: 4 }} />
        </div>
      ))}
    </div>
  );
}
