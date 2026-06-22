import { defineConfig } from '@hey-api/openapi-ts';

// Generates the type-safe API client into src/client from the backend's OpenAPI
// schema. Treat src/client as build output: regenerate with `npm run
// generate-client` while the backend serves http://localhost:8000/openapi.json.
export default defineConfig({
  input: 'http://localhost:8000/openapi.json',
  output: {
    path: './src/client',
  },
  plugins: ['@hey-api/client-axios', '@hey-api/typescript', '@hey-api/sdk'],
});
