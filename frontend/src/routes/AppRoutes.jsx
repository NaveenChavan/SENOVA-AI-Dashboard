import { lazy, Suspense } from 'react'
import { Routes, Route, Navigate } from 'react-router-dom'
import Loader from '../components/common/Loader'
import AuthGuard from '../components/common/AuthGuard'
import GuestGuard from '../components/common/GuestGuard'

const Upload = lazy(() => import('../pages/Upload'))
const Dashboard = lazy(() => import('../pages/Dashboard'))
const Login = lazy(() => import('../pages/Login'))
const Signup = lazy(() => import('../pages/Signup'))
const ForgotPassword = lazy(() => import('../pages/ForgotPassword'))
const ResetPasswordConfirm = lazy(() => import('../pages/ResetPasswordConfirm'))
const VerifyEmail = lazy(() => import('../pages/VerifyEmail'))

export default function AppRoutes() {
  return (
    <Suspense fallback={<Loader message="Loading page…" />}>
      <Routes>
        <Route path="/login" element={<GuestGuard><Login /></GuestGuard>} />
        <Route path="/signup" element={<GuestGuard><Signup /></GuestGuard>} />
        <Route path="/forgot-password" element={<GuestGuard><ForgotPassword /></GuestGuard>} />
        <Route path="/reset-password-confirm" element={<ResetPasswordConfirm />} />
        <Route path="/verify-email" element={<VerifyEmail />} />
        <Route path="/" element={<Navigate to="/upload" replace />} />
        <Route path="/upload" element={<AuthGuard><Upload /></AuthGuard>} />
        <Route path="/dashboard" element={<AuthGuard><Dashboard /></AuthGuard>} />
        <Route path="*" element={<Navigate to="/upload" replace />} />
      </Routes>
    </Suspense>
  )
}
