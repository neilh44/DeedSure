import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDropzone } from 'react-dropzone'
import { Upload, File, X, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import api from '@/lib/api'

interface UploadedFile {
  id?: string
  name: string
  size: number
  progress: number
  status: 'uploading' | 'success' | 'error'
  error?: string
}

export default function DocumentUpload() {
  const [files, setFiles] = useState<UploadedFile[]>([])
  const [isUploading, setIsUploading] = useState(false)
  const { toast } = useToast()
  const navigate = useNavigate()

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    accept: {
      'application/pdf': ['.pdf'],
      'image/jpeg': ['.jpg', '.jpeg'],
      'image/png': ['.png'],
    },
    onDrop: (acceptedFiles) => {
      const newFiles = acceptedFiles.map((file) => ({
        name: file.name,
        size: file.size,
        progress: 0,
        status: 'uploading' as const,
      }))
      
      setFiles((prev) => [...prev, ...newFiles])
      handleUpload(acceptedFiles)
    },
    disabled: isUploading,
  })

  const handleUpload = async (acceptedFiles: File[]) => {
    setIsUploading(true)
    
    for (let i = 0; i < acceptedFiles.length; i++) {
      const file = acceptedFiles[i]
      const formData = new FormData()
      formData.append('file', file)
      
      try {
        // Update progress to simulate upload
        setFiles((prev) => 
          prev.map((f, index) => 
            index === files.length + i
              ? { ...f, progress: 50 }
              : f
          )
        )
        
        // Send the file to the API
        const response = await api.post('/documents/upload', formData, {
          headers: {
            'Content-Type': 'multipart/form-data',
          },
        })
        
        // Update the file status with the response
        setFiles((prev) => 
          prev.map((f, index) => 
            index === files.length + i
              ? { 
                  ...f, 
                  id: response.data.id,
                  progress: 100, 
                  status: 'success' 
                }
              : f
          )
        )
      } catch (error) {
        console.error('Upload error:', error)
        
        // Update the file status with error
        setFiles((prev) => 
          prev.map((f, index) => 
            index === files.length + i
              ? { 
                  ...f, 
                  progress: 0, 
                  status: 'error',
                  error: 'Upload failed'
                }
              : f
          )
        )
        
        toast({
          variant: 'destructive',
          title: 'Upload failed',
          description: 'There was an error uploading your file.',
        })
      }
    }
    
    setIsUploading(false)
  }

  const removeFile = (index: number) => {
    setFiles((prev) => prev.filter((_, i) => i !== index))
  }

  const finishUpload = () => {
    const hasSuccessfulUploads = files.some((file) => file.status === 'success')
    
    if (hasSuccessfulUploads) {
      toast({
        title: 'Upload complete',
        description: 'Your documents have been uploaded successfully.',
      })
      navigate('/documents')
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Upload Documents</h1>
      
      <div className="rounded-lg border border-dashed border-gray-300 bg-white p-8">
        <div 
          {...getRootProps()} 
          className={`flex flex-col items-center justify-center space-y-4 rounded-lg border-2 border-dashed border-gray-300 bg-gray-50 p-12 text-center hover:bg-gray-100 ${
            isDragActive ? 'border-blue-500 bg-blue-50' : ''
          }`}
        >
          <input {...getInputProps()} />
          <Upload className="h-12 w-12 text-gray-400" />
          <div className="space-y-1">
            <p className="text-lg font-medium">
              {isDragActive
                ? 'Drop the files here...'
                : 'Drag and drop your files here'}
            </p>
            <p className="text-sm text-gray-500">
              or click to browse from your computer
            </p>
          </div>
          <p className="text-xs text-gray-400">
            Supports PDF, JPG, and PNG files
          </p>
        </div>
        
        {files.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-medium">Uploads</h3>
            <ul className="mt-3 divide-y divide-gray-200">
              {files.map((file, index) => (
                <li key={index} className="flex items-center justify-between py-3">
                  <div className="flex items-center">
                    <File className="mr-2 h-5 w-5 text-gray-400" />
                    <div className="flex-1 truncate">
                      <div className="flex items-center space-x-3">
                        <p className="truncate text-sm font-medium text-gray-900">{file.name}</p>
                        {file.status === 'uploading' && (
                          <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-medium text-blue-800">
                            Uploading... {file.progress}%
                          </span>
                        )}
                        {file.status === 'success' && (
                          <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
                            <Check className="mr-1 h-3 w-3" />
                            Complete
                          </span>
                        )}
                        {file.status === 'error' && (
                          <span className="inline-flex items-center rounded-full bg-red-100 px-2.5 py-0.5 text-xs font-medium text-red-800">
                            Error
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-gray-500">
                        {(file.size / 1024).toFixed(2)} KB
                      </p>
                    </div>
                  </div>
                  {file.status !== 'uploading' && (
                    <button
                      onClick={() => removeFile(index)}
                      className="ml-4 rounded-full p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-500"
                    >
                      <X className="h-4 w-4" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
            
            <div className="mt-4 flex justify-end">
              <Button
                onClick={finishUpload}
                disabled={isUploading || !files.some(f => f.status === 'success')}
              >
                {isUploading ? 'Uploading...' : 'Done'}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
