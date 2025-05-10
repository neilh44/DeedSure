import { Navigate, Outlet, useLocation } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'

export default function AuthLayout() {
  const { isAuthenticated, isLoading } = useAuth()
  const location = useLocation()

  // If still loading, show nothing
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p>Loading...</p>
      </div>
    )
  }

  // If user is authenticated, redirect to dashboard
  if (isAuthenticated) {
    return <Navigate to="/" replace />
  }

  return (
    <div className="flex min-h-screen bg-gray-50">
      <div className="flex flex-1 flex-col justify-center px-4 py-12 sm:px-6 lg:flex-none lg:px-20 xl:px-24">
        <div className="mx-auto w-full max-w-sm lg:w-96">
          <div className="mb-10">
            <h2 className="mt-6 text-3xl font-extrabold text-gray-900">
              {location.pathname === '/login' ? 'Sign in to your account' : 'Create your account'}
            </h2>
            <p className="mt-2 text-sm text-gray-600">
              {location.pathname === '/login' ? (
                <>
                  Or{' '}
                  <a href="/register" className="font-medium text-blue-600 hover:text-blue-500">
                    create a new account
                  </a>
                </>
              ) : (
                <>
                  Already have an account?{' '}
                  <a href="/login" className="font-medium text-blue-600 hover:text-blue-500">
                    Sign in
                  </a>
                </>
              )}
            </p>
          </div>
          
          <Outlet />
        </div>
      </div>
      <div className="relative hidden flex-1 lg:block">
        <div className="absolute inset-0 bg-gradient-to-r from-blue-800 to-indigo-900" />
        <div className="flex h-full items-center justify-center px-8">
          <div className="text-center text-white">
            <h1 className="text-4xl font-bold">Legal Title Search</h1>
            <p className="mt-4 text-xl">
              Generate comprehensive title search reports with AI assistance
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
