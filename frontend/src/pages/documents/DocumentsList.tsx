import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { File, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import api from '@/lib/api'

interface DocumentItem {
  id: string
  filename: string
  upload_date: string
  status: string
}

export function DocumentsList() {
  const [documents, setDocuments] = useState<DocumentItem[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchDocuments = async () => {
      try {
        setIsLoading(true)
        const response = await api.get('/documents')
        setDocuments(response.data)
      } catch (error) {
        console.error('Error fetching documents:', error)
        setError('Failed to load documents')
      } finally {
        setIsLoading(false)
      }
    }

    fetchDocuments()
  }, [])

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Documents</h1>
        <Link to="/documents/upload">
          <Button>
            <Plus className="mr-2 h-4 w-4" />
            Upload Document
          </Button>
        </Link>
      </div>

      <div className="rounded-lg border border-gray-200 bg-white">
        <div className="grid grid-cols-12 gap-4 border-b border-gray-200 bg-gray-50 px-6 py-3">
          <div className="col-span-7 text-sm font-medium text-gray-900">File Name</div>
          <div className="col-span-2 text-sm font-medium text-gray-900">Status</div>
          <div className="col-span-2 text-sm font-medium text-gray-900">Uploaded</div>
          <div className="col-span-1 text-sm font-medium text-gray-900"></div>
        </div>

        {isLoading ? (
          <div className="flex h-64 items-center justify-center">
            <p className="text-gray-500">Loading documents...</p>
          </div>
        ) : error ? (
          <div className="flex h-64 items-center justify-center">
            <p className="text-red-500">{error}</p>
          </div>
        ) : documents.length === 0 ? (
          <div className="flex h-64 items-center justify-center">
            <p className="text-gray-500">No documents found</p>
          </div>
        ) : (
          <div className="max-h-[calc(100vh-250px)] overflow-y-auto">
            {documents.map((doc) => (
              <div
                key={doc.id}
                className="grid grid-cols-12 gap-4 border-b border-gray-200 px-6 py-4 hover:bg-gray-50"
              >
                <div className="col-span-7 flex items-center">
                  <File className="mr-3 h-5 w-5 flex-shrink-0 text-gray-400" />
                  <span className="truncate text-sm text-gray-900">{doc.filename}</span>
                </div>
                <div className="col-span-2">
                  <span className={`inline-flex rounded-full px-2 py-0.5 text-xs font-medium ${
                    doc.status === 'processed' 
                      ? 'bg-green-100 text-green-800' 
                      : doc.status === 'uploaded' 
                      ? 'bg-blue-100 text-blue-800' 
                      : 'bg-gray-100 text-gray-800'
                  }`}>
                    {doc.status}
                  </span>
                </div>
                <div className="col-span-2 text-sm text-gray-500">
                  {doc.upload_date ? new Date(doc.upload_date).toLocaleDateString() : 'Invalid Date'}
                </div>
                <div className="col-span-1 text-right">
                  <Link
                    to={`/documents/${doc.id}`}
                    className="text-sm font-medium text-blue-600 hover:text-blue-800"
                  >
                    View
                  </Link>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}