import { useEffect, useState, lazy } from "react";
import { useSearchParams, Link } from "react-router-dom";
import { Helmet } from "react-helmet-async";
import useSalesStore from "../store/useSalesStore";
import api from "../services/api";
import Loader from "../components/common/Loader";
import ErrorBoundary from "../components/common/ErrorBoundary";
import SummaryStats from "../components/dashboard/SummaryStats";
import Card from "../components/common/Card";

const RowErrorsBanner = lazy(() => import("../components/dashboard/RowErrorsBanner"));
const TopItems = lazy(() => import("../components/dashboard/TopItems"));
const CategoryPieChart = lazy(() => import("../components/charts/CategoryPieChart"));
const LineChart = lazy(() => import("../components/charts/LineChart"));
const DeadStockTable = lazy(() => import("../components/dashboard/DeadStockTable"));
const PnLReportTable = lazy(() => import("../components/dashboard/PnLReportTable"));
const TransactionLedgerTable = lazy(() => import("../components/dashboard/TransactionLedgerTable"));

const DATE_FILTERS = [
  { value: "today",   label: "Today",        minSpanDays: 1 },
  { value: "week",    label: "Last 7 Days",  minSpanDays: 8 },
  { value: "30days",  label: "Last 30 Days", minSpanDays: 31 },
  { value: "month",   label: "This Month",   minSpanDays: 8 },
  { value: "all",     label: "All Time",     minSpanDays: 1 },
];

/**
 * A filter is meaningless (shows the exact same rows as "All Time") when
 * the data's actual span doesn't exceed the filter's window. Disabling it
 * — rather than hiding it — keeps the UI predictable and lets a tooltip
 * explain why, instead of the numbers just mysteriously matching another
 * tab. "Today" and "All Time" always make sense, so they're never disabled.
 */
function isFilterMeaningful(filter, spanDays) {
  if (filter.value === "today" || filter.value === "all") return true;
  if (!spanDays) return true; // unknown span (e.g. old file, no date_range) — don't block anything
  return spanDays >= filter.minSpanDays;
}

const VIEW_TABS = [
  { value: "charts", label: "Charts" },
  { value: "report", label: "Financial Report" },
];

function LoadingSkeleton() {
  return (
    <div className="space-y-6 sm:space-y-8 animate-pulse">
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3 sm:gap-4">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="card-gradient rounded-xl p-4 sm:p-6">
            <div className="h-3 rounded w-20 mb-3" style={{ background: 'var(--bg-skeleton)' }} />
            <div className="h-7 rounded w-28" style={{ background: 'var(--bg-skeleton)' }} />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 sm:gap-6">
        <div className="card-gradient rounded-xl p-4 sm:p-6">
          <div className="h-4 rounded w-48 mb-6" style={{ background: 'var(--bg-skeleton)' }} />
          <div className="h-64 rounded" style={{ background: 'var(--bg-skeleton)', opacity: 0.5 }} />
        </div>
        <div className="card-gradient rounded-xl p-4 sm:p-6">
          <div className="h-4 rounded w-40 mb-6" style={{ background: 'var(--bg-skeleton)' }} />
          <div className="h-64 rounded" style={{ background: 'var(--bg-skeleton)', opacity: 0.5 }} />
        </div>
      </div>
      <div className="card-gradient rounded-xl p-4 sm:p-6">
        <div className="h-4 rounded w-36 mb-6" style={{ background: 'var(--bg-skeleton)' }} />
        <div className="h-64 rounded" style={{ background: 'var(--bg-skeleton)', opacity: 0.5 }} />
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [searchParams] = useSearchParams();
  const fileId = searchParams.get("fileId");

  const {
    data, isLoading, error, fetchAnalytics,
    caReport, caReportLoading, caReportError, fetchCAReport,
    ledgerPage, ledgerLoading, fetchLedgerPage,
    dateRange,
  } = useSalesStore();
  const [exporting, setExporting] = useState(false);
  const [dateFilter, setDateFilter] = useState("30days");
  const [activeTab, setActiveTab] = useState("charts");
  const [ledgerPageNum, setLedgerPageNum] = useState(1);

  useEffect(() => {
    if (!fileId) return;
    const currentFileId = useSalesStore.getState().fileId;
    if (currentFileId !== fileId) {
      useSalesStore.setState({ fileId });
    }
    fetchAnalytics(fileId, dateFilter);
  }, [fileId, dateFilter, fetchAnalytics]);

  // If the current filter becomes meaningless once we know the data's
  // actual span (e.g. default "Last 30 Days" but the file only covers 4
  // days), fall back to "All Time" automatically instead of leaving a
  // disabled filter selected.
  useEffect(() => {
    if (!dateRange?.span_days) return;
    const current = DATE_FILTERS.find((f) => f.value === dateFilter);
    if (current && !isFilterMeaningful(current, dateRange.span_days)) {
      setDateFilter("all");
    }
  }, [dateRange, dateFilter]);

  // The Financial Report tab is fetched lazily, only once the user
  // switches to it — no point loading P&L + ledger data on every visit
  // to the Charts tab.
  useEffect(() => {
    if (!fileId || activeTab !== "report") return;
    fetchCAReport(fileId, dateFilter);
    setLedgerPageNum(1);
    fetchLedgerPage(fileId, { timeFilter: dateFilter, page: 1, pageSize: 50 });
  }, [fileId, dateFilter, activeTab, fetchCAReport, fetchLedgerPage]);

  const handleLedgerPageChange = (page) => {
    setLedgerPageNum(page);
    fetchLedgerPage(fileId, { timeFilter: dateFilter, page, pageSize: 50 });
  };

  const analyticsData = data;

  const isEmpty = data && data.summary && data.summary.revenue?.value === 0 && data.top_items?.length === 0

  const exportPDF = async () => {
    if (!fileId) return;
    setExporting(true);
    try {
      // Backend generates a real, structured PDF (Platypus tables — a
      // proper P&L statement, category ledger, top items, dead stock, and
      // detailed transaction register) rather than a screenshot of the
      // page. `api` attaches the Firebase auth token automatically.
      const response = await api.get(`/analytics/${fileId}/report.pdf`, {
        params: { time_filter: dateFilter },
        responseType: "blob",
      });

      const blobUrl = URL.createObjectURL(response.data);
      const link = document.createElement("a");
      link.href = blobUrl;
      link.download = `senova-financial-report-${fileId.slice(0, 8)}.pdf`;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(blobUrl);
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
        <div className="p-4 rounded-full mb-4" style={{ background: 'rgba(239,68,68,0.1)' }}>
          <svg
            className="w-8 h-8"
            style={{ color: 'var(--accent-red)' }}
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
      <div className="flex flex-col items-center justify-center py-16 md:py-24 text-center px-4">
        <Helmet>
          <title>No Data — SENOVA Digital Lab</title>
        </Helmet>
        <div className="card max-w-sm w-full p-8">
          <div
            className="w-12 h-12 rounded-2xl flex items-center justify-center mx-auto mb-4"
            style={{ background: 'var(--accent-blue-glow)' }}
          >
            <svg className="w-6 h-6" style={{ color: 'var(--accent-blue)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 17V7m3 10v-4m3 4v-7m3-4v11M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z" />
            </svg>
          </div>
          <p className="font-medium mb-1" style={{ color: 'var(--text-primary)' }}>No analytics yet</p>
          <p className="text-sm mb-5" style={{ color: 'var(--text-secondary)' }}>
            Upload a sales file to generate your first dashboard.
          </p>
          <Link to="/upload" className="btn-primary inline-block">
            Upload a file
          </Link>
        </div>
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
            style={{background: 'var(--bg-input)', border: '1px solid var(--border-subtle)'}}>
            {DATE_FILTERS.map((f) => {
              const meaningful = isFilterMeaningful(f, dateRange?.span_days);
              const disabled = !meaningful;
              return (
                <button
                  key={f.value}
                  onClick={() => !disabled && setDateFilter(f.value)}
                  disabled={disabled}
                  aria-pressed={dateFilter === f.value}
                  title={
                    disabled
                      ? `Your data only spans ${dateRange?.span_days} day${dateRange?.span_days === 1 ? '' : 's'} — this filter would show the same results as "All Time".`
                      : undefined
                  }
                  style={{
                    padding: '10px 14px',
                    minHeight: 40,
                    borderRadius: 8,
                    fontSize: '0.8rem',
                    fontWeight: 500,
                    whiteSpace: 'nowrap',
                    transition: 'all 0.2s',
                    cursor: disabled ? 'not-allowed' : 'pointer',
                    opacity: disabled ? 0.35 : 1,
                    background: dateFilter === f.value
                      ? 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))'
                      : 'transparent',
                    color: dateFilter === f.value ? 'var(--text-on-accent)' : 'var(--text-secondary)',
                    boxShadow: dateFilter === f.value ? '0 2px 8px var(--accent-blue-glow)' : 'none',
                  }}
                >
                  {f.label}
                </button>
              );
            })}
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

      {dateRange?.span_days > 0 && dateRange.span_days < 8 && (
        <div
          className="card-gradient rounded-xl px-4 sm:px-5 py-3 flex items-start gap-3"
          style={{ border: '1px solid rgba(2,132,199,0.3)' }}
          role="note"
        >
          <svg className="w-5 h-5 shrink-0 mt-0.5" style={{ color: 'var(--accent-blue)' }} fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <p className="text-sm" style={{ color: 'var(--text-secondary)' }}>
            Your uploaded data covers only <strong style={{ color: 'var(--text-primary)' }}>{dateRange.span_days} day{dateRange.span_days === 1 ? '' : 's'}</strong>{' '}
            ({dateRange.min_date} to {dateRange.max_date}). Filters wider than that are disabled above since
            they'd show identical results to "All Time" — this isn't a bug, there just isn't more data to compare yet.
          </p>
        </div>
      )}

      {analyticsData?.errors?.length > 0 && (
        <ErrorBoundary>
          <RowErrorsBanner errors={analyticsData.errors} />
        </ErrorBoundary>
      )}

      <div
        role="tablist"
        aria-label="Dashboard view"
        className="flex items-center gap-1 p-1 rounded-xl w-fit"
        style={{ background: 'var(--bg-input)', border: '1px solid var(--border-subtle)' }}
      >
        {VIEW_TABS.map((t) => (
          <button
            key={t.value}
            role="tab"
            aria-selected={activeTab === t.value}
            onClick={() => setActiveTab(t.value)}
            className="text-xs sm:text-sm"
            style={{
              padding: '10px 14px',
              minHeight: 40,
              borderRadius: 8,
              fontWeight: 500,
              transition: 'all 0.2s',
              background: activeTab === t.value
                ? 'linear-gradient(135deg, var(--accent-blue-strong), var(--accent-blue))'
                : 'transparent',
              color: activeTab === t.value ? 'var(--text-on-accent)' : 'var(--text-secondary)',
            }}
          >
            {t.label}
          </button>
        ))}
      </div>

      {activeTab === "charts" && (
        <div className="space-y-6 sm:space-y-8">
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
      )}

      {activeTab === "report" && (
        <div className="space-y-6 sm:space-y-8">
          {caReportError && (
            <div className="card-gradient rounded-xl px-4 py-3" style={{ border: '1px solid rgba(239,68,68,0.3)' }}>
              <p className="text-sm" style={{ color: 'var(--accent-red)' }}>{caReportError}</p>
            </div>
          )}
          <ErrorBoundary>
            {caReportLoading && !caReport ? (
              <Loader message="Building financial report…" />
            ) : (
              <PnLReportTable report={caReport} />
            )}
          </ErrorBoundary>
          <ErrorBoundary>
            <TransactionLedgerTable
              ledgerPage={ledgerPage}
              loading={ledgerLoading}
              onPageChange={handleLedgerPageChange}
            />
          </ErrorBoundary>
        </div>
      )}
    </section>
  );
}