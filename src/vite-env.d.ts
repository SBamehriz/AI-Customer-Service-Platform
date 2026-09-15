/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Base URL of the backend. Empty or unset means the same origin. */
  readonly VITE_API_URL?: string;
  /** Overrides the GitHub link on the landing page. */
  readonly VITE_REPO_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
