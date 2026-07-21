import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Loader from '../components/common/Loader'
import AuthGuard from '../components/common/AuthGuard'

const Upload = lazy(() => import('../pages/Upload'))
const Dashboard = lazy(() => import('../pages/Dashboard'))
const Login = lazy(() => import('../pages/Login'))

export default function AppRoutes() {
  return (
    <Suspense fallback={<Loader message="Loading page…" />}>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/" element={<Navigate to="/upload" replace />} />
        <Route path="/upload" element={<AuthGuard><Upload /></AuthGuard>} />
        <Route path="/dashboard" element={<AuthGuard><Dashboard /></AuthGuard>} />
        <Route path="*" element={<Navigate to="/upload" replace />} />
      </Routes>
    </Suspense>
  )
}
