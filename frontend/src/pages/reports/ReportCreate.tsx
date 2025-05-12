import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { File, Check } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { useToast } from '@/components/ui/use-toast'
import api from '@/lib/api'
import { formatDate } from '@/lib/utils'

interface Document {
  id: string
  filename: string
  upload_date: string
  status: string
}

export default function ReportCreate() {
  const [documents, setDocuments] = useState<Document[]>([])
  const [selectedDocuments, setSelectedDocuments] = useState<string[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isGenerating, setIsGenerating] = useState(false)
  const { toast } = useToast()
  const navigate = useNavigate()

  useEffect(() => {
    const fetchDocuments = async () => {
      try {
        const response = await api.get('/documents')
        setDocuments(response.data)
      } catch (error) {
        console.error('Error fetching documents:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchDocuments()
  }, [])

  const toggleDocumentSelection = (documentId: string) => {
    setSelectedDocuments((prev) => {
      if (prev.includes(documentId)) {
        return prev.filter((id) => id !== documentId)
      }
      return [...prev, documentId]
    })
  }

  const handleGenerateReport = async () => {
    if (selectedDocuments.length === 0) {
      toast({
        variant: 'destructive',
        title: 'No documents selected',
        description: 'Please select at least one document to generate a report.',
      })
      return
    }

    setIsGenerating(true)
    try {
      const response = await api.post('/reports/generate', {
        document_ids: selectedDocuments,
      })
      
      toast({
        title: 'Report generation started',
        description: 'Your report is being generated.',
      })
      
      navigate(`/reports/${response.data.id}`)
    } catch (error) {
      console.error('Error generating report:', error)
      toast({
        variant: 'destructive',
        title: 'Report generation failed',
        description: 'There was an error generating your report.',
      })
    } finally {
      setIsGenerating(false)
    }
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Create Title Report</h1>
      
      <div className="rounded-lg bg-white p-6 shadow">
        <h2 className="text-lg font-medium text-gray-900">Select Documents</h2>
        <p className="mt-1 text-sm text-gray-500">
          Choose the property documents to include in your title report.
        </p>
        
        <div className="mt-6">
          {isLoading ? (
            <p className="text-sm text-gray-500">Loading documents...</p>
          ) : documents.length === 0 ? (
            <div className="rounded-lg border border-dashed border-gray-300 p-6 text-center">
              <p className="text-sm text-gray-500">No documents found</p>
              <Button className="mt-4" asChild>
                <a href="/documents/upload">Upload Documents</a>
              </Button>
            </div>
          ) : (
            <div className="overflow-hidden rounded-md border">
              <ul className="divide-y divide-gray-200 max-h-[calc(100vh-350px)] overflow-y-auto pr-2">
                {documents.map((document) => (
                  <li key={document.id} className="flex items-center p-4 hover:bg-gray-50">
                    <div className="flex h-6 items-center">
                      <input
                        type="checkbox"
                        id={`document-${document.id}`}
                        checked={selectedDocuments.includes(document.id)}
                        onChange={() => toggleDocumentSelection(document.id)}
                        className="h-4 w-4 rounded border-gray-300 text-blue-600 focus:ring-blue-500"
                      />
                    </div>
                    <label
                      htmlFor={`document-${document.id}`}
                      className="ml-3 flex flex-1 cursor-pointer items-center"
                    >
                      <File className="mr-2 h-5 w-5 text-gray-400" />
                      <div className="flex-1">
                        <p className="text-sm font-medium text-gray-900">{document.filename}</p>
                        <p className="text-xs text-gray-500">
                          Uploaded on {formatDate(document.upload_date)}
                        </p>
                      </div>
                      {document.status === 'processed' && (
                        <span className="inline-flex items-center rounded-full bg-green-100 px-2.5 py-0.5 text-xs font-medium text-green-800">
                          <Check className="mr-1 h-3 w-3" />
                          Processed
                        </span>
                      )}
                    </label>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        
        <div className="mt-6 flex justify-end">
          <Button
            onClick={handleGenerateReport}
            disabled={selectedDocuments.length === 0 || isGenerating}
          >
            {isGenerating ? 'Generating...' : 'Generate Title Report'}
          </Button>
        </div>
      </div>
    </div>
  )
}