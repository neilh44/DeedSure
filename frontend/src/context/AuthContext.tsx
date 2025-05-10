import { createContext, useContext, useState, useEffect, ReactNode } from 'react'
import { useNavigate } from 'react-router-dom'
import api from '@/lib/api'

// Configure timeout for API requests
api.defaults.timeout = 30000 // Increase to 30 seconds

interface User {
  id: string
  email: string
  fullName?: string
  firmName?: string
}

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string, fullName: string, firmName: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextType | undefined>(undefined)

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const navigate = useNavigate()

  // Check if user is already logged in
  useEffect(() => {
    const checkAuth = async () => {
      const token = localStorage.getItem('token')
      if (token) {
        try {
          const response = await api.get('/users/me')
          setUser(response.data)
        } catch (error) {
          console.error('Auth check error:', error)
          localStorage.removeItem('token')
        }
      }
      setIsLoading(false)
    }

    checkAuth()
  }, [])

  const login = async (email: string, password: string): Promise<void> => {
    try {
      console.log('Attempting login with:', { email })
      
      const response = await api.post('/auth/login-json', {
        email,
        password,
      })
      
      console.log('Login response:', response.data)
      
      const { access_token, user } = response.data
      
      // Set token in localStorage
      localStorage.setItem('token', access_token)
      
      // Also update the Authorization header immediately
      api.defaults.headers.common['Authorization'] = `Bearer ${access_token}`
      
      console.log('Token stored and header set')
      
      setUser(user)
      navigate('/')
    } catch (error: any) {
      console.error('Login error details:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      })
      
      throw new Error(error.response?.data?.message || 'Invalid email or password')
    }
  }

  const register = async (email: string, password: string, fullName: string, firmName: string) => {
    try {
      console.log('Starting registration process for:', { email, fullName, firmName })
      
      // Step 1: Register the user in auth system
      console.log('Step 1: Creating auth account')
      
      // Create a specific instance for this request with a longer timeout
      const registerResponse = await api.post('/auth/register', {
        email,
        password,
        full_name: fullName,
        firm_name: firmName,
      }, {
        timeout: 60000 // 60-second timeout for registration specifically
      })
      
      console.log('Auth account created:', registerResponse.data)
      
      // Step 2: Login to get the token
      console.log('Step 2: Logging in to get token')
      
      try {
        await login(email, password)
        console.log('Login successful')
        
        // Step 3: Add delay to ensure token propagation
        console.log('Step 3: Waiting for token propagation')
        await new Promise(resolve => setTimeout(resolve, 2000))
        
        // Step 4: Create user profile - with error handling and retries
        console.log('Step 4: Creating user profile')
        
        let retryCount = 0;
        const maxRetries = 3;
        
        const createProfile = async (): Promise<void> => {
          try {
            console.log('Current auth header:', api.defaults.headers.common['Authorization'])
            
            const profileResponse = await api.post('/users', {
              email: email,
              full_name: fullName,
              firm_name: firmName,
            }, {
              timeout: 30000 // 30-second timeout for profile creation
            })
            
            console.log('Profile created successfully:', profileResponse.data)
          } catch (profileError: any) {
            console.error('Profile creation error:', {
              message: profileError.message,
              response: profileError.response?.data,
              status: profileError.response?.status
            })
            
            if (retryCount < maxRetries) {
              retryCount++;
              console.log(`Retrying profile creation (${retryCount}/${maxRetries})...`);
              await new Promise(resolve => setTimeout(resolve, 2000)); // Wait 2 seconds before retry
              return createProfile();
            } else {
              console.log('Maximum retries reached. Continuing despite profile creation issues.');
              // We're already logged in, so we can continue
            }
          }
        };
        
        await createProfile();
        
      } catch (loginError) {
        console.error('Login after registration failed:', loginError)
        throw new Error('Account created but login failed')
      }
    } catch (error: any) {
      console.error('Registration error details:', {
        message: error.message,
        response: error.response?.data,
        status: error.response?.status
      })
      
      // More descriptive error message
      const errorMessage = error.response?.data?.detail || 
                          error.response?.data?.message || 
                          'Registration failed. Please try again later.';
                          
      throw new Error(errorMessage);
    }
  }

  const logout = () => {
    console.log('Logging out')
    
    localStorage.removeItem('token')
    delete api.defaults.headers.common['Authorization']
    
    setUser(null)
    navigate('/login')
  }

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        isAuthenticated: !!user,
        login,
        register,
        logout,
      }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}