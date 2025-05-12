import { useEffect, useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { ArrowLeft, FileText, Download, Printer } from 'lucide-react'
import { Button } from '@/components/ui/button'
import api from '@/lib/api'
import { formatDate } from '@/lib/utils'

interface Report {
  id: string
  title: string
  created_at: string
  status: string
  content: string
  document_ids: string[]
}

export default function ReportView() {
  const { id } = useParams<{ id: string }>()
  const [report, setReport] = useState<Report | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)

  useEffect(() => {
    const fetchReport = async () => {
      try {
        const response = await api.get(`/reports/${id}`)
        setReport(response.data)
        
        // If the report is still processing, set up polling
        if (response.data.status === 'processing') {
          if (!pollingInterval) {
            const interval = window.setInterval(() => {
              fetchReport()
            }, 5000) // Poll every 5 seconds
            setPollingInterval(interval)
          }
        } else if (pollingInterval) {
          // If report is no longer processing, stop polling
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      } catch (error) {
        console.error('Error fetching report:', error)
        setError('Failed to load report')
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      } finally {
        setIsLoading(false)
      }
    }

    fetchReport()
    
    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [id, pollingInterval])

  const handlePrint = () => {
    window.print()
  }

  const handleDownload = () => {
    // Create a blob with the report content
    const blob = new Blob([report?.content || ''], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    
    // Create a temporary anchor element and trigger download
    const a = document.createElement('a')
    a.href = url
    a.download = `${report?.title || 'report'}.txt`
    document.body.appendChild(a)
    a.click()
    
    // Clean up
    URL.revokeObjectURL(url)
    document.body.removeChild(a)
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <p className="text-gray-500">Loading report...</p>
      </div>
    )
  }

  if (error || !report) {
    return (
      <div className="rounded-lg bg-white p-6 shadow">
        <div className="text-center">
          <h3 className="mt-2 text-lg font-medium text-gray-900">Report not found</h3>
          <p className="mt-1 text-sm text-gray-500">{error || 'The report you requested could not be found.'}</p>
          <div className="mt-6">
            <Link to="/reports">
              <Button>Go back to reports</Button>
            </Link>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-6 pb-10">
      <div className="flex items-center space-x-4">
        <Link to="/reports" className="text-blue-600 hover:text-blue-800">
          <ArrowLeft className="h-5 w-5" />
        </Link>
        <h1 className="text-2xl font-bold tracking-tight">{report.title}</h1>
      </div>
      
      <div className="flex flex-col gap-8 lg:flex-row">
        {/* Report info */}
        <div className="lg:w-1/3">
          <div className="rounded-lg bg-white p-6 shadow">
            <h2 className="text-lg font-medium text-gray-900">Report Information</h2>
            <dl className="mt-4 divide-y divide-gray-200">
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Title</dt>
                <dd className="text-gray-900">{report.title}</dd>
              </div>
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Created</dt>
                <dd className="text-gray-900">{formatDate(report.created_at)}</dd>
              </div>
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Status</dt>
                <dd className="text-gray-900">
                  <span className={`inline-flex rounded-full px-2 text-xs font-semibold leading-5 ${
                    report.status === 'completed' 
                      ? 'bg-green-100 text-green-800' 
                      : report.status === 'processing'
                      ? 'bg-blue-100 text-blue-800'
                      : 'bg-yellow-100 text-yellow-800'
                  }`}>
                    {report.status}
                  </span>
                </dd>
              </div>
              <div className="flex justify-between py-3 text-sm">
                <dt className="text-gray-500">Documents</dt>
                <dd className="text-gray-900">{report.document_ids.length}</dd>
              </div>
            </dl>
            
            <div className="mt-6 space-y-3">
              <Button
                variant="outline"
                className="flex w-full items-center"
                onClick={handleDownload}
                disabled={report.status !== 'completed'}
              >
                <Download className="mr-2 h-4 w-4" />
                Download
              </Button>
              <Button
                variant="outline"
                className="flex w-full items-center"
                onClick={handlePrint}
                disabled={report.status !== 'completed'}
              >
                <Printer className="mr-2 h-4 w-4" />
                Print
              </Button>
            </div>
          </div>
        </div>
        
        {/* Report content */}
        <div className="flex-1">
          <div className="rounded-lg bg-white p-6 shadow">
            <div className="mb-4 flex items-center justify-between">
              <h2 className="text-lg font-medium text-gray-900">Title Report</h2>
              {report.status === 'processing' && (
                <div className="rounded-full bg-blue-100 px-3 py-1 text-xs font-medium text-blue-800">
                  Processing...
                </div>
              )}
            </div>
            
            {report.status === 'processing' ? (
              <div className="flex h-96 items-center justify-center rounded-lg border border-gray-200 bg-gray-50 p-8">
                <div className="text-center">
                  <FileText className="mx-auto h-12 w-12 text-gray-400" />
                  <h3 className="mt-2 text-sm font-medium text-gray-900">Generating Report</h3>
                  <p className="mt-1 text-sm text-gray-500">
                    Your title report is being generated. This may take a few minutes.
                  </p>
                </div>
              </div>
            ) : (
              <div className="prose prose-blue max-w-none rounded-lg border border-gray-200 bg-white p-8">
                <div className="max-h-[calc(100vh-300px)] overflow-y-auto whitespace-pre-wrap pr-2">
                  {report.content}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
