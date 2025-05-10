import { useState } from 'react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuth } from '@/context/AuthContext'
import { Bell, File, FileText, Home, LogOut, Menu, User, X } from 'lucide-react'
import { Button } from '@/components/ui/button'

export default function DashboardLayout() {
  const { isAuthenticated, isLoading, user, logout } = useAuth()
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // If still loading, show nothing
  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p>Loading...</p>
      </div>
    )
  }

  // If user is not authenticated, redirect to login
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />
  }

  return (
    <div className="h-screen overflow-hidden bg-gray-100">
      {/* Mobile sidebar */}
      <div className={`fixed inset-0 z-40 flex md:hidden ${sidebarOpen ? '' : 'translate-x-full'} transform transition-transform duration-300 ease-in-out`}>
        <div className="relative flex w-full max-w-xs flex-1 flex-col bg-white pt-5 pb-4">
          <div className="absolute top-0 right-0 -mr-12 pt-2">
            <button
              type="button"
              className="ml-1 flex h-10 w-10 items-center justify-center rounded-full focus:outline-none focus:ring-2 focus:ring-inset focus:ring-white"
              onClick={() => setSidebarOpen(false)}
            >
              <span className="sr-only">Close sidebar</span>
              <X className="h-6 w-6 text-white" />
            </button>
          </div>
          <div className="flex flex-shrink-0 items-center px-4">
            <h1 className="text-xl font-bold text-gray-900">Legal Title Search</h1>
          </div>
          <div className="mt-5 h-0 flex-1 overflow-y-auto">
            <nav className="space-y-1 px-2">
              <a href="/" className="group flex items-center rounded-md px-2 py-2 text-base font-medium text-gray-900 hover:bg-gray-100 hover:text-gray-900">
                <Home className="mr-4 h-6 w-6 text-gray-500 group-hover:text-gray-500" />
                Dashboard
              </a>
              <a href="/documents" className="group flex items-center rounded-md px-2 py-2 text-base font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
                <File className="mr-4 h-6 w-6 text-gray-400 group-hover:text-gray-500" />
                Documents
              </a>
              <a href="/reports" className="group flex items-center rounded-md px-2 py-2 text-base font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
                <FileText className="mr-4 h-6 w-6 text-gray-400 group-hover:text-gray-500" />
                Reports
              </a>
              <a href="/profile" className="group flex items-center rounded-md px-2 py-2 text-base font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
                <User className="mr-4 h-6 w-6 text-gray-400 group-hover:text-gray-500" />
                Profile
              </a>
            </nav>
          </div>
        </div>
        <div className="w-14 flex-shrink-0" aria-hidden="true">
          {/* Force sidebar to shrink to fit close icon */}
        </div>
      </div>

      {/* Static sidebar for desktop */}
      <div className="hidden md:fixed md:inset-y-0 md:flex md:w-64 md:flex-col">
        <div className="flex flex-grow flex-col overflow-y-auto border-r border-gray-200 bg-white pt-5">
          <div className="flex flex-shrink-0 items-center px-4">
            <h1 className="text-xl font-bold text-gray-900">Legal Title Search</h1>
          </div>
          <div className="mt-5 flex flex-grow flex-col">
            <nav className="flex-1 space-y-1 px-2 pb-4">
              <a href="/" className="group flex items-center rounded-md px-2 py-2 text-sm font-medium text-gray-900 hover:bg-gray-100 hover:text-gray-900">
                <Home className="mr-3 h-5 w-5 text-gray-500 group-hover:text-gray-500" />
                Dashboard
              </a>
              <a href="/documents" className="group flex items-center rounded-md px-2 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
                <File className="mr-3 h-5 w-5 text-gray-400 group-hover:text-gray-500" />
                Documents
              </a>
              <a href="/reports" className="group flex items-center rounded-md px-2 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
                <FileText className="mr-3 h-5 w-5 text-gray-400 group-hover:text-gray-500" />
                Reports
              </a>
              <a href="/profile" className="group flex items-center rounded-md px-2 py-2 text-sm font-medium text-gray-600 hover:bg-gray-100 hover:text-gray-900">
                <User className="mr-3 h-5 w-5 text-gray-400 group-hover:text-gray-500" />
                Profile
              </a>
            </nav>
          </div>
        </div>
      </div>

      {/* Main content */}
      <div className="flex flex-1 flex-col md:pl-64">
        <div className="sticky top-0 z-10 flex h-16 flex-shrink-0 bg-white shadow">
          <button
            type="button"
            className="border-r border-gray-200 px-4 text-gray-500 focus:outline-none focus:ring-2 focus:ring-inset focus:ring-indigo-500 md:hidden"
            onClick={() => setSidebarOpen(true)}
          >
            <span className="sr-only">Open sidebar</span>
            <Menu className="h-6 w-6" />
          </button>
          <div className="flex flex-1 justify-between px-4">
            <div className="flex flex-1"></div>
            <div className="ml-4 flex items-center md:ml-6">
              <button
                type="button"
                className="rounded-full bg-white p-1 text-gray-400 hover:text-gray-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2"
              >
                <span className="sr-only">View notifications</span>
                <Bell className="h-6 w-6" />
              </button>

              {/* Profile dropdown */}
              <div className="ml-3 flex items-center">
                <div className="ml-3">
                  <div className="text-base font-medium text-gray-800">{user?.fullName || user?.email}</div>
                  <div className="text-sm font-medium text-gray-500">{user?.firmName || 'Legal Professional'}</div>
                </div>
                <Button variant="ghost" size="icon" onClick={logout} className="ml-3">
                  <LogOut className="h-5 w-5" />
                </Button>
              </div>
            </div>
          </div>
        </div>

        <main className="flex-1">
          <div className="py-6">
            <div className="mx-auto max-w-7xl px-4 sm:px-6 md:px-8">
              <Outlet />
            </div>
          </div>
        </main>
      </div>
    </div>
  )
}
