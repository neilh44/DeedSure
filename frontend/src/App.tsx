import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Toaster } from '@/components/ui/toaster'
import { AuthProvider } from '@/context/AuthContext' // Add this import

// Layouts
import AuthLayout from '@/components/layouts/AuthLayout'
import DashboardLayout from '@/components/layouts/DashboardLayout'

// Pages
import Login from '@/pages/auth/Login'
import Register from '@/pages/auth/Register'
import Dashboard from '@/pages/dashboard/Dashboard'
import DocumentsList from '@/pages/documents/DocumentsList'
import DocumentUpload from '@/pages/documents/DocumentUpload'
import DocumentView from '@/pages/documents/DocumentView'
import ReportsList from '@/pages/reports/ReportsList'
import ReportCreate from '@/pages/reports/ReportCreate'
import ReportView from '@/pages/reports/ReportView'
import UserProfile from '@/pages/users/UserProfile'

// Create a client
const queryClient = new QueryClient()

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <Router>
        <AuthProvider> {/* Add this wrapper */}
          <Routes>
            {/* Auth Routes */}
            <Route element={<AuthLayout />}>
              <Route path="/login" element={<Login />} />
              <Route path="/register" element={<Register />} />
            </Route>
            
            {/* Dashboard Routes */}
            <Route element={<DashboardLayout />}>
              <Route path="/" element={<Dashboard />} />
              <Route path="/documents" element={<DocumentsList />} />
              <Route path="/documents/upload" element={<DocumentUpload />} />
              <Route path="/documents/:id" element={<DocumentView />} />
              <Route path="/reports" element={<ReportsList />} />
              <Route path="/reports/create" element={<ReportCreate />} />
              <Route path="/reports/:id" element={<ReportView />} />
              <Route path="/profile" element={<UserProfile />} />
            </Route>
          </Routes>
          <Toaster />
        </AuthProvider> {/* Close the wrapper */}
      </Router>
    </QueryClientProvider>
  )
}

export default App