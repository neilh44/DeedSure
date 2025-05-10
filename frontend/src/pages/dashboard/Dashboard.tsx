import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { File, FileText, Upload } from 'lucide-react'
// Removed the unused Button import
import api from '@/lib/api'

interface Document {
  id: string
  filename: string
  upload_date: string
  status: string
}

interface Report {
  id: string
  title: string
  created_at: string
  status: string
}

export default function Dashboard() {
  const [recentDocuments, setRecentDocuments] = useState<Document[]>([])
  const [recentReports, setRecentReports] = useState<Report[]>([])
  const [isLoading, setIsLoading] = useState(true)

  useEffect(() => {
    const fetchData = async () => {
      try {
        const [documentsRes, reportsRes] = await Promise.all([
          api.get('/documents'),
          api.get('/reports')
        ])
        
        setRecentDocuments(documentsRes.data.slice(0, 5))
        setRecentReports(reportsRes.data.slice(0, 5))
      } catch (error) {
        console.error('Error fetching dashboard data:', error)
      } finally {
        setIsLoading(false)
      }
    }

    fetchData()
  }, [])

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
      
      {/* Quick actions */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <div className="overflow-hidden rounded-lg bg-white shadow">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <Upload className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-gray-500">Upload Documents</dt>
                  <dd>
                    <div className="text-lg font-medium text-gray-900">Add property documents</div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
          <div className="bg-gray-50 px-5 py-3">
            <div className="text-sm">
              <Link to="/documents/upload" className="font-medium text-blue-700 hover:text-blue-900">
                Upload new documents
              </Link>
            </div>
          </div>
        </div>

        <div className="overflow-hidden rounded-lg bg-white shadow">
          <div className="p-5">
            <div className="flex items-center">
              <div className="flex-shrink-0">
                <FileText className="h-6 w-6 text-gray-400" />
              </div>
              <div className="ml-5 w-0 flex-1">
                <dl>
                  <dt className="truncate text-sm font-medium text-gray-500">Generate Report</dt>
                  <dd>
                    <div className="text-lg font-medium text-gray-900">Create title search report</div>
                  </dd>
                </dl>
              </div>
            </div>
          </div>
          <div className="bg-gray-50 px-5 py-3">
            <div className="text-sm">
              <Link to="/reports/create" className="font-medium text-blue-700 hover:text-blue-900">
                Start new report
              </Link>
            </div>
          </div>
        </div>
      </div>

      {/* Recent activity */}
      <h2 className="text-lg font-medium leading-6 text-gray-900">Recent Activity</h2>
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        {/* Recent documents */}
        <div>
          <div className="overflow-hidden rounded-lg bg-white shadow">
            <div className="p-6">
              <h3 className="text-base font-medium text-gray-900">Recent Documents</h3>
              <div className="mt-6 flow-root">
                <ul className="-my-5 divide-y divide-gray-200">
                  {isLoading ? (
                    <p className="py-4 text-sm text-gray-500">Loading...</p>
                  ) : recentDocuments.length === 0 ? (
                    <p className="py-4 text-sm text-gray-500">No documents found</p>
                  ) : (
                    recentDocuments.map((document) => (
                      <li key={document.id} className="py-4">
                        <div className="flex items-center space-x-4">
                          <div className="flex-shrink-0">
                            <File className="h-8 w-8 text-gray-400" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-gray-900">{document.filename}</p>
                            <p className="truncate text-sm text-gray-500">
                              Uploaded on {new Date(document.upload_date).toLocaleDateString()}
                            </p>
                          </div>
                          <div>
                            <Link
                              to={`/documents/${document.id}`}
                              className="inline-flex items-center rounded-full border border-gray-300 bg-white px-2.5 py-0.5 text-sm font-medium leading-5 text-gray-700 shadow-sm hover:bg-gray-50"
                            >
                              View
                            </Link>
                          </div>
                        </div>
                      </li>
                    ))
                  )}
                </ul>
              </div>
              <div className="mt-6">
                <Link
                  to="/documents"
                  className="flex w-full items-center justify-center rounded-md bg-white px-3 py-2 text-sm font-medium text-blue-700 shadow-sm hover:bg-gray-50"
                >
                  View all
                </Link>
              </div>
            </div>
          </div>
        </div>

        {/* Recent reports */}
        <div>
          <div className="overflow-hidden rounded-lg bg-white shadow">
            <div className="p-6">
              <h3 className="text-base font-medium text-gray-900">Recent Reports</h3>
              <div className="mt-6 flow-root">
                <ul className="-my-5 divide-y divide-gray-200">
                  {isLoading ? (
                    <p className="py-4 text-sm text-gray-500">Loading...</p>
                  ) : recentReports.length === 0 ? (
                    <p className="py-4 text-sm text-gray-500">No reports found</p>
                  ) : (
                    recentReports.map((report) => (
                      <li key={report.id} className="py-4">
                        <div className="flex items-center space-x-4">
                          <div className="flex-shrink-0">
                            <FileText className="h-8 w-8 text-gray-400" />
                          </div>
                          <div className="min-w-0 flex-1">
                            <p className="truncate text-sm font-medium text-gray-900">{report.title}</p>
                            <p className="truncate text-sm text-gray-500">
                              Created on {new Date(report.created_at).toLocaleDateString()}
                            </p>
                          </div>
                          <div>
                            <Link
                              to={`/reports/${report.id}`}
                              className="inline-flex items-center rounded-full border border-gray-300 bg-white px-2.5 py-0.5 text-sm font-medium leading-5 text-gray-700 shadow-sm hover:bg-gray-50"
                            >
                              View
                            </Link>
                          </div>
                        </div>
                      </li>
                    ))
                  )}
                </ul>
              </div>
              <div className="mt-6">
                <Link
                  to="/reports"
                  className="flex w-full items-center justify-center rounded-md bg-white px-3 py-2 text-sm font-medium text-blue-700 shadow-sm hover:bg-gray-50"
                >
                  View all
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}