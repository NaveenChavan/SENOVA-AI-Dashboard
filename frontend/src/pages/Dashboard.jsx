import { useEffect, useRef, useState } from "react";
import { useSearchParams, Link } from "react-router-dom";
import html2canvas from "html2canvas";
import jsPDF from "jspdf";
import useSalesStore from "../store/useSalesStore";
import Loader from "../components/common/Loader";
import ErrorBoundary from "../components/common/ErrorBoundary";
import SummaryStats from "../components/dashboard/SummaryStats";
import TopItems from "../components/dashboard/TopItems";
import CategoryPieChart from "../components/charts/CategoryPieChart";
import LineChart from "../components/charts/LineChart";
import DeadStockTable from "../components/dashboard/DeadStockTable";
import RowErrorsBanner from "../components/dashboard/RowErrorsBanner";
import Card from "../components/common/Card";

const DATE_FILTERS = [
  { value: "all", label: "All Time" },
  { value: "month", label: "This Month" },
  { value: "week", label: "Last 7 Days" },
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
  }, [fileId, dateFilter]);

  const analyticsData = data;

  const exportPDF = async () => {
    if (!reportRef.current) return;
    setExporting(true);
    try {
      const canvas = await html2canvas(reportRef.current, {
        scale: 2,
        useCORS: true,
        backgroundColor: "#0a1128",
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

  if (isLoading && !data) return <LoadingSkeleton />;
  if (isLoading && data) return <Loader message="Refreshing analytics…" />;

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
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
        <p className="text-slate-200 text-lg font-medium mb-2">
          Something went wrong
        </p>
        <p className="text-slate-500 mb-6">{error}</p>
        <Link
          to="/upload"
          className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2 transition-colors"
        >
          Upload a new file
        </Link>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <p className="text-slate-500 mb-4">No analytics data loaded yet.</p>
        <Link
          to="/upload"
          className="text-emerald-400 hover:text-emerald-300 underline underline-offset-2 transition-colors"
        >
          Upload a file to get started
        </Link>
      </div>
    );
  }

  return (
    <section className="space-y-8">
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h1 className="text-3xl font-bold text-slate-100">Dashboard</h1>
          <p className="text-slate-500 mt-1 text-sm">
            Snapshot of your uploaded sales data. All values in INR (₹).
          </p>
        </div>

        <div className="flex items-center gap-3">
          <div className="relative">
            <select
              value={dateFilter}
              onChange={(e) => setDateFilter(e.target.value)}
              className="appearance-none bg-slate-800 border border-slate-600 text-slate-200 text-sm rounded-lg pl-4 pr-10 py-2.5 focus:outline-none focus:ring-2 focus:ring-emerald-400/50 focus:border-emerald-400/50 cursor-pointer"
            >
              {DATE_FILTERS.map((f) => (
                <option key={f.value} value={f.value}>
                  {f.label}
                </option>
              ))}
            </select>
            <svg
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </div>

          <button
            onClick={exportPDF}
            disabled={exporting}
            className="px-5 py-2.5 rounded-lg bg-emerald-500 hover:bg-emerald-400 text-white font-medium transition-all duration-200 shadow-lg shadow-emerald-500/20 hover:shadow-emerald-400/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
          >
            <svg
              className="w-4 h-4"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            {exporting ? "Generating…" : "Download Report (PDF)"}
          </button>
        </div>
      </div>

      {analyticsData?.errors?.length > 0 && (
        <RowErrorsBanner errors={analyticsData.errors} />
      )}

      <div ref={reportRef} className="space-y-8">
        <SummaryStats summary={analyticsData.summary} />

        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          <TopItems items={analyticsData.top_items} />
          <Card title="Revenue by Category">
            <ErrorBoundary>
              {analyticsData.categories?.length > 0 ? (
                <CategoryPieChart data={analyticsData.categories} />
              ) : (
                <div className="flex items-center justify-center h-[280px] text-slate-500 text-sm">
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
              <div className="flex items-center justify-center h-[280px] text-slate-500 text-sm">
                No trend data
              </div>
            )}
          </ErrorBoundary>
        </Card>

        <DeadStockTable items={analyticsData.dead_stock} />
      </div>
    </section>
  );
}
