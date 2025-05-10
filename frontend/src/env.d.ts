/// <reference types="vite/client" />

interface ImportMetaEnv {
    readonly VITE_API_URL: string;
    readonly VITE_SUPABASE_URL: string;
    readonly VITE_SUPABASE_ANON_KEY: string;
    readonly VITE_SECRET_KEY: string;
    // Add any other environment variables as needed
  }
  
  interface ImportMeta {
    readonly env: ImportMetaEnv;
  }