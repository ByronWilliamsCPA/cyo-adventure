/// <reference types="node" />
/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_API_URL: string
  readonly VITE_DEBUG?: string
  readonly VITE_ANALYTICS_ID?: string
  readonly VITE_SENTRY_DSN?: string
  readonly VITE_SUPABASE_URL: string
  readonly VITE_SUPABASE_ANON_KEY: string
  readonly VITE_ENABLE_APPLE_OAUTH?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
