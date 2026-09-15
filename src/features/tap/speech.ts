/** Browser speech recognition, wrapped. */

interface SpeechRecognitionAlternative {
  transcript: string;
  confidence: number;
}

interface SpeechRecognitionResult {
  readonly length: number;
  isFinal: boolean;
  [index: number]: SpeechRecognitionAlternative;
}

interface SpeechRecognitionResultList {
  readonly length: number;
  [index: number]: SpeechRecognitionResult;
}

interface SpeechRecognitionEvent extends Event {
  resultIndex: number;
  results: SpeechRecognitionResultList;
}

interface SpeechRecognitionErrorEvent extends Event {
  error: string;
  message: string;
}

interface SpeechRecognitionLike extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start(): void;
  stop(): void;
  abort(): void;
  onresult: ((event: SpeechRecognitionEvent) => void) | null;
  onerror: ((event: SpeechRecognitionErrorEvent) => void) | null;
  onend: (() => void) | null;
}

type SpeechRecognitionConstructor = new () => SpeechRecognitionLike;

declare global {
  interface Window {
    SpeechRecognition?: SpeechRecognitionConstructor;
    webkitSpeechRecognition?: SpeechRecognitionConstructor;
  }
}

export function speechRecognitionSupported(): boolean {
  return typeof window !== 'undefined' && Boolean(window.SpeechRecognition ?? window.webkitSpeechRecognition);
}

export interface SpeechListenerOptions {
  /** Called with each completed utterance. */
  onFinal: (text: string) => void;
  /** Called with the guess so far, for a live caption. */
  onInterim?: (text: string) => void;
  onError?: (message: string) => void;
  lang?: string;
}

export interface SpeechListener {
  start: () => void;
  stop: () => void;
}

export function createSpeechListener(options: SpeechListenerOptions): SpeechListener | null {
  const Constructor = window.SpeechRecognition ?? window.webkitSpeechRecognition;
  if (!Constructor) return null;

  const recognition = new Constructor();
  recognition.continuous = true;
  recognition.interimResults = true;
  recognition.lang = options.lang ?? navigator.language ?? 'en-US';

  let wanted = false;

  recognition.onresult = (event) => {
    let interim = '';
    for (let index = event.resultIndex; index < event.results.length; index += 1) {
      const result = event.results[index];
      const text = result[0]?.transcript ?? '';
      if (result.isFinal) {
        const finalText = text.trim();
        if (finalText) options.onFinal(finalText);
      } else {
        interim += text;
      }
    }
    options.onInterim?.(interim.trim());
  };

  recognition.onerror = (event) => {
    if (event.error === 'no-speech' || event.error === 'aborted') return;
    options.onError?.(event.error);
  };

  recognition.onend = () => {
    if (wanted) {
      try {
        recognition.start();
      } catch {
        // Already restarting. The next end event will try again.
      }
    }
  };

  return {
    start() {
      wanted = true;
      try {
        recognition.start();
      } catch {
        // Starting twice throws, which is harmless here.
      }
    },
    stop() {
      wanted = false;
      recognition.stop();
    },
  };
}
