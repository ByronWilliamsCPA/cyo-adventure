import { defineConfig } from '@hey-api/openapi-ts'

// Generates the type-safe API client into src/client from the backend's OpenAPI
// schema. Treat src/client as build output: regenerate with `npm run
// generate-client` while the backend serves http://localhost:8000/openapi.json.
//
// OPENAPI_INPUT lets CI point this at a schema file dumped straight from the
// FastAPI app (no live server needed) to check the committed client for drift;
// local dev is unaffected since the env var is normally unset.
export default defineConfig({
  input: process.env.OPENAPI_INPUT ?? 'http://localhost:8000/openapi.json',
  output: {
    path: './src/client',
  },
  plugins: ['@hey-api/client-axios', '@hey-api/typescript', '@hey-api/sdk'],
})
