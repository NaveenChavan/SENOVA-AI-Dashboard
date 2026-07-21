import { useEffect, useRef, useState, lazy } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import useSalesStore from "../store/useSalesStore";
import Loader from "../components/common/Loader";
import ErrorBoundary from "../components/common/ErrorBoundary";
import SummaryStats from "../components/dashboard/SummaryStats";
import Card from "../components/common/Card";

const RowErrorsBanner = lazy(() => import("../components/dashboard/RowErrorsBanner"));
const TopItems = lazy(() => import("../components/dashboard/TopItems"));
const CategoryPieChart = lazy(() => import("../components/charts/CategoryPieChart"));
const LineChart = lazy(() => import("../components/charts/LineChart"));
const DeadStockTable = lazy(() => import("../components/dashboard/DeadStockTable"));

const DATE_FILTERS = [
  { value: "all",     label: "All Time" },
  { value: "30days",  label: "Last 30 Days" },
  { value: "month",   label: "This Month" },
  { value: "week",    label: "Last 7 Days" },
];

function LoadingSkeleton() {
  return (
    <div className="space-y-8 animate-pulse">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card-gradient rounded-xl p-6">
            <div className="h-3 bg-slate-700/60 rounded w-20 mb-3" />
            <div className="h-7 bg-slate-700/60 rounded w-28" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="card-gradient rounded-xl p-6">
          <div className="h-4 bg-slate-700/60 rounded w-48 mb-6" />
          <div className="h-64 bg-slate-700/30 rounded" />
        </div>
        <div className="card-gradient rounded-xl p-6">
          <div className="h-4 bg-slate-700/60 rounded w-40 mb-6" />
          <div className="h-64 bg-slate-700/30 rounded" />
        </div>
      </div>
      <div className="card-gradient rounded-xl p-6">
        <div className="h-4 bg-slate-700/60 rounded w-36 mb-6" />
        <div className="h-64 bg-slate-700/30 rounded" />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const fileId = searchParams.get("fileId");

  const { data, isLoading, error, fetchAnalytics } = useSalesStore();
  const reportRef = useRef(null);
  const [exporting, setExporting] = useState(false);
  const [dateFilter, setDateFilter] = useState("all");

  useEffect(() => {
    if (!fileId) return;
    const currentFileId = useSalesStore.getState().fileId;
    if (currentFileId !== fileId) {
      useSalesStore.setState({ fileId });
    }
    fetchAnalytics(fileId, dateFilter);
  }, [fileId, dateFilter, fetchAnalytics]);

  const analyticsData = data;

  const isEmpty = data && data.summary && data.summary.revenue?.value === 0 && data.top_items?.length === 0

  const exportPDF = async () => {
    if (!reportRef.current) return;
    setExporting(true);
    try {
      const [html2canvasModule, jsPDFModule] = await Promise.all([
        import("html2canvas"),
        import("jspdf"),
      ]);
      const html2canvas = html2canvasModule.default;
      const jsPDF = jsPDFModule.default;

      const canvas = await html2canvas(reportRef.current, {
        scale: 2,
        useCORS: true,
        backgroundColor: "#050d1a",
      });
      const imgData = canvas.toDataURL("image/png");
      const pdf = new jsPDF("p", "mm", "a4");
      const pageWidth = pdf.internal.pageSize.getWidth();
      const imgWidth = pageWidth - 20;
      const imgHeight = (canvas.height * imgWidth) / canvas.width;
      pdf.addImage(imgData, "PNG", 10, 10, imgWidth, imgHeight);
      pdf.save("senova-report.pdf");
    } catch (err) {
      console.error("PDF export failed:", err);
    } finally {
      setExporting(false);
    }
  };

  if (isEmpty) return (
    <section className="pt-8">
      <Helmet>
        <title>No Data — SENOVA Digital Lab</title>
      </Helmet>
      <div className="flex flex-col items-center justify-center py-24 text-center card max-w-md mx-auto mt-12">
        <span className="text-4xl mb-4">📭</span>
        <h3 className="text-lg font-semibold mb-2" style={{color: 'var(--text-primary)'}}>
          No data for this period
        </h3>
        <p className="text-sm mb-6" style={{color: 'var(--text-secondary)'}}>
          The selected date filter returned no matching records.
          Try switching to "All Time" or a wider window.
        </p>
        <button onClick={() => setDateFilter('all')} className="btn-primary">
          Reset to All Time
        </button>
      </div>
    </section>
  )

  if (isLoading && !data) return <LoadingSkeleton />;
  if (isLoading && data) return <Loader message="Refreshing analytics…" />;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-12 md:py-24 text-center px-4">
        <Helmet>
          <title>Error — SENOVA Digital Lab</title>
        </Helmet>
        <div className="p-4 rounded-full bg-red-500/10 mb-4">
          <svg
            className="w-8 h-8 text-red-400"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
            />
          </svg>
        </div>
        <p className="text-lg font-medium mb-2" style={{color:'var(--text-primary)'}}>
          Something went wrong
        </p>
        <p className="mb-6" style={{color:'var(--text-secondary)'}}>{error}</p>
        <Link
          to="/upload"
          className="underline underline-offset-2 transition-colors"
          style={{color:'var(--accent-blue)'}}
        >
          Upload a new file
        </Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-12 md:py-24 text-center px-4">
        <Helmet>
          <title>No Data — SENOVA Digital Lab</title>
        </Helmet>
        <p className="mb-4" style={{color:'var(--text-secondary)'}}>No analytics data loaded yet.</p>
        <Link
          to="/upload"
          className="underline underline-offset-2 transition-colors"
          style={{color:'var(--accent-blue)'}}
        >
          Upload a file to get started
        </Link>
      </div>
    );
  }

  return (
    <section className="space-y-6 sm:space-y-8">
      <Helmet>
        <title>Dashboard — SENOVA Digital Lab | Retail & MSME Analytics</title>
        <meta name="description" content="Real-time AI retail analytics dashboard showing revenue, profit, top-selling items, dead stock analysis, and daily sales trends for your business." />
      </Helmet>

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 mb-8">
        <div>
          <h1 className="text-2xl font-bold" style={{color: 'var(--text-primary)'}}>
            Analytics Overview
          </h1>
          <p className="text-sm mt-0.5" style={{color: 'var(--text-secondary)'}}>
            All values in INR (₹) · {DATE_FILTERS.find(f => f.value === dateFilter)?.label}
          </p>
        </div>

        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3">
          <div
            role="group"
            aria-label="Filter analytics by date range"
            className="flex items-center gap-1 p-1 rounded-xl overflow-x-auto"
            style={{background: 'rgba(10,22,45,0.8)', border: '1px solid var(--border-subtle)'}}>
            {DATE_FILTERS.map((f) => (
              <button
                key={f.value}
                onClick={() => setDateFilter(f.value)}
                aria-pressed={dateFilter === f.value}
                style={{
                  padding: '6px 14px',
                  borderRadius: 8,
                  fontSize: '0.8rem',
                  fontWeight: 500,
                  whiteSpace: 'nowrap',
                  transition: 'all 0.2s',
                  background: dateFilter === f.value
                    ? 'linear-gradient(135deg, #0ea5e9, #38bdf8)'
                    : 'transparent',
                  color: dateFilter === f.value ? '#fff' : 'var(--text-secondary)',
                  boxShadow: dateFilter === f.value ? '0 2px 8px rgba(56,189,248,0.3)' : 'none',
                }}
              >
                {f.label}
              </button>
            ))}
          </div>

          <button
            onClick={exportPDF}
            disabled={exporting}
            aria-busy={exporting}
            className="btn-primary flex items-center justify-center gap-2 whitespace-nowrap"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"/>
            </svg>
            {exporting ? 'Generating…' : 'Export PDF'}
          </button>
        </div>
      </div>

      {analyticsData?.errors?.length > 0 && (
        <ErrorBoundary>
          <RowErrorsBanner errors={analyticsData.errors} />
        </ErrorBoundary>
      )}

      <div ref={reportRef} className="space-y-6 sm:space-y-8">
        <SummaryStats key={dateFilter} summary={analyticsData.summary} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <ErrorBoundary>
            <TopItems items={analyticsData.top_items} />
          </ErrorBoundary>
          <Card title="Revenue by Category">
            <ErrorBoundary>
              {analyticsData.categories?.length > 0 ? (
                <CategoryPieChart data={analyticsData.categories} />
              ) : (
                <div className="flex items-center justify-center h-64 text-sm"
                  style={{color:'var(--text-muted)'}}>
                  No category data
                </div>
              )}
            </ErrorBoundary>
          </Card>
        </div>

        <Card title="Daily Sales Trend">
          <ErrorBoundary>
            {analyticsData.daily_trend?.length > 0 ? (
              <LineChart data={analyticsData.daily_trend} />
            ) : (
              <div className="flex items-center justify-center h-64 text-sm"
                style={{color:'var(--text-muted)'}}>
                No trend data
              </div>
            )}
          </ErrorBoundary>
        </Card>

        <ErrorBoundary>
          <DeadStockTable items={analyticsData.dead_stock} />
        </ErrorBoundary>
      </div>
    </section>
  );
}