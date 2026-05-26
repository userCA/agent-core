import React, { useState, useRef, useCallback } from 'react';
import type { InputSchema, InputField } from '../../api/types';
import { useSessionStore } from '../../stores/session-store';
import { submitHumanInput } from '../../api/client';
import { fileToBase64 } from '../../utils/file';
import { useBridge } from '../../bridge/BridgeContext';
import './HitlCard.css';

interface Props {
  toolCallId: string;
  prompt: string;
  inputSchema: InputSchema;
  onSubmitted?: () => void;
}

export default function HitlCard({ toolCallId, prompt, inputSchema, onSubmitted }: Props) {
  const sessionId = useSessionStore((s) => s.sessionId);
  const bridge = useBridge();
  const [values, setValues] = useState<Record<string, unknown>>({});
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [submitted, setSubmitted] = useState(false);
  const [submitError, setSubmitError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Image upload state
  const [imageFiles, setImageFiles] = useState<Record<string, string[]>>({});
  const [uploadCounts, setUploadCounts] = useState<Record<string, number>>({});

  // Audio record state
  const [audioState, setAudioState] = useState<Record<string, { recording: boolean; url: string | null; base64: string | null }>>({});

  const handleTextChange = (name: string, value: string) => {
    setValues((p) => ({ ...p, [name]: value }));
    if (errors[name]) setErrors((p) => { const n = { ...p }; delete n[name]; return n; });
  };

  const handleSelectChange = (name: string, value: string) => {
    setValues((p) => ({ ...p, [name]: value }));
  };

  const handleImageUpload = async (field: InputField, files: FileList) => {
    const existing = imageFiles[field.name] || [];
    const max = field.max || 5;
    const remaining = max - existing.length;
    const toProcess = Array.from(files).slice(0, remaining);

    const dataUris = await Promise.all(toProcess.map(fileToBase64));
    const all = [...existing, ...dataUris];
    setImageFiles((p) => ({ ...p, [field.name]: all }));
    setUploadCounts((p) => ({ ...p, [field.name]: all.length }));
    setValues((p) => ({ ...p, [field.name]: all }));
  };

  const removeImage = (fieldName: string, idx: number) => {
    setImageFiles((p) => {
      const updated = [...(p[fieldName] || [])];
      updated.splice(idx, 1);
      setValues((v) => ({ ...v, [fieldName]: updated }));
      setUploadCounts((c) => ({ ...c, [fieldName]: updated.length }));
      return { ...p, [fieldName]: updated };
    });
  };

  const handleAudioRecord = async (field: InputField) => {
    const current = audioState[field.name];
    if (current?.recording) {
      // stop
      const bridgeStop = bridge.stopRecord;
      if (bridgeStop) {
        try {
          const result = await bridgeStop();
          const url = `data:${result.mimeType};base64,${result.base64}`;
          setAudioState((p) => ({ ...p, [field.name]: { recording: false, url, base64: result.base64 } }));
          setValues((v) => ({ ...v, [field.name]: result.base64 }));
        } catch {
          setAudioState((p) => ({ ...p, [field.name]: { recording: false, url: null, base64: null } }));
        }
      }
    } else {
      // start
      const bridgeStart = bridge.startRecord;
      if (bridgeStart) {
        await bridgeStart();
        setAudioState((p) => ({ ...p, [field.name]: { recording: true, url: null, base64: null } }));
      }
    }
  };

  const validate = (): boolean => {
    const errs: Record<string, string> = {};
    for (const field of inputSchema.fields) {
      if (field.required) {
        const val = values[field.name];
        if (val === undefined || val === null || val === '') {
          errs[field.name] = `${field.label} is required`;
        }
      }
    }
    setErrors(errs);
    return Object.keys(errs).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!validate()) return;
    if (!sessionId) return;

    setSubmitting(true);
    try {
      await submitHumanInput(sessionId, toolCallId, values);
      setSubmitted(true);
      onSubmitted?.();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Submit failed');
    } finally {
      setSubmitting(false);
    }
  };

  if (submitted) {
    return (
      <div className="hitl-card submitted">
        [x] submitted — waiting for agent...
      </div>
    );
  }

  return (
    <div className="hitl-card">
      <div className="hitl-prompt">{prompt}</div>
      <form onSubmit={handleSubmit}>
        {inputSchema.fields.map((field) => (
          <div key={field.name} className={`hitl-field ${errors[field.name] ? 'has-error' : ''}`}>
            <label htmlFor={`hitl-${field.name}`}>
              {field.label}
              {field.required && <span className="required"> *</span>}
            </label>

            {field.type === 'select' && (
              <select
                id={`hitl-${field.name}`}
                value={(values[field.name] as string) || ''}
                onChange={(e) => handleSelectChange(field.name, e.target.value)}
              >
                <option value="">-- choose --</option>
                {field.options?.map((opt) => (
                  <option key={opt.value} value={opt.value}>{opt.label}</option>
                ))}
              </select>
            )}

            {field.type === 'textarea' && (
              <textarea
                id={`hitl-${field.name}`}
                value={(values[field.name] as string) || ''}
                onChange={(e) => handleTextChange(field.name, e.target.value)}
                placeholder={field.placeholder}
                rows={4}
              />
            )}

            {field.type === 'text' && (
              <input
                id={`hitl-${field.name}`}
                type="text"
                value={(values[field.name] as string) || ''}
                onChange={(e) => handleTextChange(field.name, e.target.value)}
                placeholder={field.placeholder}
              />
            )}

            {field.type === 'image_upload' && (
              <div className="image-upload-area">
                <label className="upload-btn">
                  {uploadCounts[field.name]
                    ? `[+] selected ${uploadCounts[field.name]}/${field.max || 5}`
                    : `[+] choose images (max ${field.max || 5})`}
                  <input
                    id={`hitl-${field.name}`}
                    type="file"
                    accept={field.accept || 'image/*'}
                    multiple
                    hidden
                    onChange={(e) => {
                      if (e.target.files) handleImageUpload(field, e.target.files);
                    }}
                  />
                </label>
                <div className="thumb-grid">
                  {(imageFiles[field.name] || []).map((dataUri, idx) => (
                    <div key={idx} className="thumb-item">
                      <img src={dataUri} alt={`upload ${idx + 1}`} />
                      <button type="button" className="thumb-remove" onClick={() => removeImage(field.name, idx)}>
                        [x]
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {field.type === 'audio_record' && (
              <div className="audio-record-area">
                <button
                  type="button"
                  className={`btn record-btn ${audioState[field.name]?.recording ? 'recording' : ''}`}
                  onMouseDown={() => handleAudioRecord(field)}
                  onMouseUp={() => handleAudioRecord(field)}
                  onTouchStart={() => handleAudioRecord(field)}
                  onTouchEnd={() => handleAudioRecord(field)}
                >
                  {audioState[field.name]?.recording ? '[!] recording...' : '[rec] hold to record'}
                </button>
                {audioState[field.name]?.url && (
                  <audio controls src={audioState[field.name].url!} />
                )}
              </div>
            )}

            {errors[field.name] && (
              <div className="field-error">{errors[field.name]}</div>
            )}
          </div>
        ))}

        {submitError && <div className="submit-error">[!] {submitError}</div>}

        <button type="submit" className="btn btn-primary" disabled={submitting}>
          {submitting ? '[#] submitting...' : 'submit'}
        </button>
      </form>
    </div>
  );
}
