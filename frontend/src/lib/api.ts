// @/lib/api.ts
import axios, { AxiosError } from 'axios'

// Get the API URL from environment variables
const baseURL = import.meta.env.VITE_API_URL || 'https://deedsure.onrender.com/api/v1'

const api = axios.create({
  baseURL,
  headers: {
    'Content-Type': 'application/json',
  },
  withCredentials: true,
})

// Add an interceptor to include the token in requests
api.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token')
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  },
  (error) => Promise.reject(error)
)

// Helper function to test different methods on the API
export const testEndpoint = async () => {
  try {
    // Try POST method
    const postResponse = await api.post('/');
    console.log('POST response:', postResponse.data);
    return postResponse.data;
  } catch (error) {
    // Type guard to check if error is an AxiosError
    const postError = error as AxiosError;
    console.log('POST error:', postError.response?.data || postError.message);
    
    try {
      // Try GET method
      const getResponse = await api.get('/');
      console.log('GET response:', getResponse.data);
      return getResponse.data;
    } catch (error) {
      // Type guard to check if error is an AxiosError
      const getError = error as AxiosError;
      console.log('GET error:', getError.response?.data || getError.message);
      
      // You could also try other methods like PUT, DELETE if needed
      throw new Error('All attempted methods failed');
    }
  }
};

export default api;