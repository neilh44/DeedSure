import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, File, FileText } from 'lucide-react'
import { Button } from '@/components/ui/button'
import api from '@/lib/api'
import { formatDate } from '@/lib/utils'

interface Document {
  id: string
  filename: string
  content_type: string
  upload_date: string
  status: string
  extracted_text: string
}

export default function DocumentView() {
  const { id } = useParams<{ id: string }>()
  const [document, setDocument] = useState<Document | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const fetchDocument = async () => {
      try {
        setIsLoading(true)
        const response = await api.get(`/documents/${id}`)
        setDocument(response.data)
      } catch (error) {
        console.error('Error fetching document:', error)
        setError('Failed to load document')
      } finally {
        setIsLoading(false)
      }
    }

    fetchDocument()
  }, [id])

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading document...</p>
      </div>
    )
  }

  if (error || !document) {
    return (
      <div className="rounded-lg bg-white p-6 shadow">
        <div className="text-center">
          <h3 className="mt-2 text-lg font-medium text-gray-900">Document not found</h3>
          <p className="mt-1 text-sm text-gray-500">{error || 'The document you requested could not be found.'}</p>
          <div className="mt-6">
            <Link to="/documents">
              <Button>Go back to documents</Button>
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center space-x-4">
        <Link to="/documents" className="text-blue-600 hover:text-blue-800">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{document.filename}</h1>
      </div>
      
      <div className="flex flex-col gap-8 lg:flex-row">
        {/* Document info */}
        <div className="lg:w-1/3">
          <div className="rounded-lg bg-white p-6 shadow">
            <h2 className="text-lg font-medium text-gray-900">Document Information</h2>
            <dl className="mt-4 divide-y divide-gray-200">
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Filename</dt>
                <dd className="text-gray-900">{document.filename}</dd>
              </div>
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Type</dt>
                <dd className="text-gray-900">{document.content_type}</dd>
              </div>
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Uploaded</dt>
                <dd className="text-gray-900">{formatDate(document.upload_date)}</dd>
              </div>
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Status</dt>
                <dd className="text-gray-900">{document.status}</dd>
              </div>
            </dl>
            
            <div className="mt-6 flex gap-3">
              <Button variant="outline" className="w-full">
                Download
              </Button>
              <Link to="/reports/create" className="w-full">
                <Button className="w-full">
                  <FileText className="mr-2 h-4 w-4" />
                  Create Report
                </Button>
              </Link>
            </div>
          </div>
        </div>
        
        {/* Document preview */}
        <div className="flex-1">
          <div className="rounded-lg bg-white p-6 shadow">
            <h2 className="text-lg font-medium text-gray-900">Document Preview</h2>
            <div className="mt-4 overflow-hidden rounded-lg border border-gray-200">
              <div className="aspect-[1/1.4] bg-gray-100 p-4">
                <div className="flex h-full w-full items-center justify-center">
                  <File className="h-16 w-16 text-gray-400" />
                </div>
              </div>
            </div>
            
            <div className="mt-6">
              <h3 className="text-sm font-medium text-gray-900">Extracted Text</h3>
              <div className="mt-2 max-h-96 overflow-y-auto rounded-lg border border-gray-200 bg-gray-50 p-4">
                <pre className="whitespace-pre-wrap text-sm text-gray-600">
                  {document.extracted_text || 'No text content available'}
                </pre>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
