import { createClient } from '@supabase/supabase-js'

// Remove the interface declarations from this file
// (they should be in a separate env.d.ts file)

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY

const supabase = createClient(supabaseUrl, supabaseKey)

export default supabase