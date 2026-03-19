import { useState, useMemo, useCallback, useRef } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeAlpine } from "ag-grid-community";
import { getGLCodes, getSourceFiles, uploadCSV, triggerClassify } from "../api/client";
import {
  useTransactions,
  useApproveTransaction,
  useFlagTransaction,
} from "../hooks/useTransactions";
import { ConfidenceBadge, ReviewBadge } from "../components/shared/Badge";
import StatsBar from "../components/shared/StatsBar";
import ReclassifyModal from "../components/transactions/ReclassifyModal";
import ConvertToRuleModal from "../components/transactions/ConvertToRuleModal";

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeAlpine;
const PAGE_SIZE = 50;

export default function TransactionsPage() {
  const queryClient = useQueryClient();
  const gridRef = useRef(null);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("confidence");
  const [sortOrder, setSortOrder] = useState("asc");
  const [filters, setFilters] = useState({
    review_status: "",
    confidence: "",
    gl_code: "",
    vendor_search: "",
    source_file: "",
    date_from: "",
    date_to: "",
  });
  const [expandedTx, setExpandedTx] = useState(null);
  const [reclassifyTx, setReclassifyTx] = useState(null);
  const [convertTx, setConvertTx] = useState(null);

  // --- Drag-and-drop state ---
  const [dragOver, setDragOver] = useState(false);
  const [stagedFile, setStagedFile] = useState(null);
  const [uploadResult, setUploadResult] = useState(null);
  const [classifyResult, setClassifyResult] = useState(null);

  const uploadMutation = useMutation({
    mutationFn: (file) => uploadCSV(file),
    onSuccess: (data) => {
      setUploadResult(data);
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["sourceFiles"] });
    },
  });

  const classifyMutation = useMutation({
    mutationFn: (sourceFile) => triggerClassify({ source_file: sourceFile }),
    onSuccess: (data) => {
      setClassifyResult(data);
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
    },
  });

  // --- Drag-and-drop handlers ---
  const handleDragOver = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(true);
  }, []);

  const handleDragLeave = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
  }, []);

  const handleDrop = useCallback((e) => {
    e.preventDefault();
    e.stopPropagation();
    setDragOver(false);
    const files = Array.from(e.dataTransfer.files);
    const csvFile = files.find(
      (f) => f.name.endsWith(".csv") || f.type === "text/csv"
    );
    if (csvFile) {
      setStagedFile({ file: csvFile, name: csvFile.name, timestamp: new Date() });
      setUploadResult(null);
      setClassifyResult(null);
    }
  }, []);

  function handleProcess() {
    if (!stagedFile) return;
    uploadMutation.mutate(stagedFile.file);
  }
  function handleClassify() {
    if (!uploadResult) return;
    classifyMutation.mutate(uploadResult.source_file);
  }
  function handleCancel() {
    setStagedFile(null);
    setUploadResult(null);
    setClassifyResult(null);
  }

  // --- Data fetching ---
  const params = useMemo(() => {
    const p = { page, page_size: PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder };
    if (filters.review_status) p.review_status = filters.review_status;
    if (filters.confidence) p.confidence = filters.confidence;
    if (filters.gl_code) p.gl_code = filters.gl_code;
    if (filters.vendor_search) p.vendor_search = filters.vendor_search;
    if (filters.source_file) p.source_file = filters.source_file;
    if (filters.date_from) p.date_from = filters.date_from;
    if (filters.date_to) p.date_to = filters.date_to;
    return p;
  }, [page, sortBy, sortOrder, filters]);

  const { data, isLoading } = useTransactions(params);
  const { data: glCodes } = useQuery({
    queryKey: ["glCodes", 3],
    queryFn: () => getGLCodes(3),
  });
  const { data: sourceFiles } = useQuery({
    queryKey: ["sourceFiles"],
    queryFn: getSourceFiles,
  });

  const approve = useApproveTransaction();
  const flag = useFlagTransaction();

  function updateFilter(field, value) {
    setFilters((f) => ({ ...f, [field]: value }));
    setPage(1);
  }

  const transactions = data?.transactions || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  function formatAmount(val) {
    return Number(val).toLocaleString("en-US", {
      style: "currency",
      currency: "USD",
    });
  }

  // --- AG Grid column definitions ---
  const columnDefs = useMemo(
    () => [
      {
        headerName: "Date",
        field: "date",
        width: 120,
        sortable: true,
      },
      {
        headerName: "Description",
        field: "raw_description",
        flex: 2,
        minWidth: 200,
        sortable: true,
        tooltipField: "raw_description",
      },
      {
        headerName: "Amount",
        field: "amount",
        width: 130,
        sortable: true,
        type: "rightAligned",
        valueFormatter: (p) => formatAmount(p.value),
        cellClass: "font-mono",
      },
      {
        headerName: "Vendor",
        field: "vendor_name",
        width: 160,
        sortable: true,
        valueGetter: (p) => p.data.vendor_name || p.data.vendor_id || "-",
      },
      {
        headerName: "GL Code",
        field: "gl_code",
        width: 150,
        sortable: true,
        valueGetter: (p) => {
          if (!p.data.gl_code) return "-";
          const cls = p.data.gl_class ? ` (${p.data.gl_class})` : "";
          return `${p.data.gl_code}${cls}`;
        },
      },
      {
        headerName: "Confidence",
        field: "confidence",
        width: 120,
        sortable: true,
        sort: "asc",
        cellRenderer: ConfidenceCellRenderer,
      },
      {
        headerName: "Method",
        field: "method",
        width: 130,
        sortable: true,
        valueFormatter: (p) => p.value || "-",
        cellClass: "text-xs text-gray-500",
      },
      {
        headerName: "Status",
        field: "review_status",
        width: 130,
        sortable: true,
        cellRenderer: StatusCellRenderer,
      },
      {
        headerName: "Actions",
        field: "actions",
        width: 140,
        sortable: false,
        cellRenderer: ActionsCellRenderer,
        cellRendererParams: {
          onApprove: (tx) =>
            approve.mutate({ id: tx.transaction_id, data: { user_id: 1 } }),
          onReclassify: (tx) => setReclassifyTx(tx),
          onFlag: (tx) =>
            flag.mutate({ id: tx.transaction_id, data: { user_id: 1 } }),
          onConvertToRule: (tx) => setConvertTx(tx),
        },
      },
    ],
    [approve, flag]
  );

  const defaultColDef = useMemo(
    () => ({
      resizable: true,
      suppressMovable: true,
      // Disable client-side sorting — we do server-side sorting.
      // Returning 0 keeps AG Grid from reordering rows while still showing sort indicators.
      comparator: () => 0,
    }),
    []
  );

  // Handle AG Grid sort events → server-side sorting
  const onSortChanged = useCallback(() => {
    const gridApi = gridRef.current?.api;
    if (!gridApi) return;
    const sortModel = gridApi.getColumnState().filter((c) => c.sort);
    if (sortModel.length > 0) {
      const col = sortModel[0];
      setSortBy(col.colId);
      setSortOrder(col.sort);
      setPage(1);
    }
  }, []);

  const onRowClicked = useCallback((event) => {
    const tx = event.data;
    setExpandedTx((prev) => {
      if (prev?.id === tx.id) {
        // Deselect
        event.api.deselectAll();
        return null;
      }
      // Select this row
      event.node.setSelected(true, true);
      return tx;
    });
  }, []);

  // Click outside grid clears selection
  const handleOutsideClick = useCallback((e) => {
    // If click is inside the grid or the detail panel, ignore
    if (e.target.closest('.ag-root-wrapper') || e.target.closest('[data-detail-panel]')) return;
    setExpandedTx(null);
    gridRef.current?.api?.deselectAll();
  }, []);

  const getRowClass = useCallback((params) => {
    if (!params.data?.is_expense) return "opacity-40";
    return "";
  }, []);

  return (
    <div
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={handleOutsideClick}
      className="relative"
    >
      {/* Drag overlay */}
      {dragOver && (
        <div className="pointer-events-none fixed inset-0 z-40 flex items-center justify-center bg-blue-500/10">
          <div className="rounded-2xl border-4 border-dashed border-blue-400 bg-white/90 px-16 py-12 text-center shadow-lg">
            <p className="text-2xl font-semibold text-blue-600">
              Drop CSV file here
            </p>
            <p className="mt-1 text-sm text-blue-400">
              Accepted format: .csv with Date, Description, Amount columns
            </p>
          </div>
        </div>
      )}

      <h2 className="mb-4 text-xl font-semibold text-gray-800">Transactions</h2>

      {/* Staged file card */}
      {stagedFile && (
        <StagedFileCard
          stagedFile={stagedFile}
          uploadResult={uploadResult}
          classifyResult={classifyResult}
          isUploading={uploadMutation.isPending}
          isClassifying={classifyMutation.isPending}
          uploadError={uploadMutation.error}
          classifyError={classifyMutation.error}
          onProcess={handleProcess}
          onClassify={handleClassify}
          onCancel={handleCancel}
        />
      )}

      <StatsBar />

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Batch
          </label>
          <select
            value={filters.source_file}
            onChange={(e) => updateFilter("source_file", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">All Batches</option>
            {(sourceFiles || []).map((sf) => (
              <option key={sf} value={sf}>
                {sf}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Review Status
          </label>
          <select
            value={filters.review_status}
            onChange={(e) => updateFilter("review_status", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">All</option>
            <option value="Unreviewed">Unreviewed</option>
            <option value="Approved">Approved</option>
            <option value="Reclassified">Reclassified</option>
            <option value="Flagged">Flagged</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Confidence
          </label>
          <select
            value={filters.confidence}
            onChange={(e) => updateFilter("confidence", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">All</option>
            <option value="High">High</option>
            <option value="Medium">Medium</option>
            <option value="Low">Low</option>
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            GL Code
          </label>
          <select
            value={filters.gl_code}
            onChange={(e) => updateFilter("gl_code", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">All</option>
            {(glCodes || []).map((g) => (
              <option key={g.gl_code} value={g.gl_code}>
                {g.gl_code} - {g.description || g.gl_class}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Vendor Search
          </label>
          <input
            type="text"
            value={filters.vendor_search}
            onChange={(e) => updateFilter("vendor_search", e.target.value)}
            placeholder="Search vendor..."
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Date From
          </label>
          <input
            type="date"
            value={filters.date_from}
            onChange={(e) => updateFilter("date_from", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Date To
          </label>
          <input
            type="date"
            value={filters.date_to}
            onChange={(e) => updateFilter("date_to", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          />
        </div>
      </div>

      {/* AG Grid Table */}
      <div className="rounded-lg border border-gray-200" style={{ width: "100%", height: 600 }}>
        <AgGridReact
          ref={gridRef}
          theme={gridTheme}
          rowData={transactions}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          animateRows={true}
          rowSelection={{ mode: "singleRow", enableClickSelection: false, hideDisabledCheckboxes: true, checkboxes: false }}
          getRowClass={getRowClass}
          onSortChanged={onSortChanged}
          onRowClicked={onRowClicked}
          suppressCellFocus={true}
          loading={isLoading}
          overlayNoRowsTemplate="<span class='text-gray-400 py-8'>No transactions found.</span>"
        />
      </div>

      {/* Detail panel for selected row */}
      {expandedTx && (
        <div data-detail-panel className="mt-2 rounded-lg border border-blue-200 bg-blue-50/30 p-4">
          <div className="flex items-center justify-between mb-3">
            <h3 className="font-semibold text-gray-700">
              Transaction {expandedTx.transaction_id}
            </h3>
            <button
              onClick={() => setExpandedTx(null)}
              className="text-gray-400 hover:text-gray-600 text-sm"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <h4 className="mb-1 font-medium text-gray-700">Reasoning</h4>
              <p className="text-gray-600">{expandedTx.reasoning || "No reasoning available."}</p>
            </div>
            <div>
              <h4 className="mb-1 font-medium text-gray-700">Details</h4>
              <dl className="space-y-1 text-xs text-gray-500">
                <div className="flex gap-2"><dt className="font-medium">Transaction ID:</dt><dd>{expandedTx.transaction_id}</dd></div>
                <div className="flex gap-2"><dt className="font-medium">Version:</dt><dd>{expandedTx.version}</dd></div>
                <div className="flex gap-2"><dt className="font-medium">Source:</dt><dd>{expandedTx.source_file || "-"}</dd></div>
                <div className="flex gap-2"><dt className="font-medium">Rule ID:</dt><dd>{expandedTx.rule_id ?? "-"}</dd></div>
                <div className="flex gap-2"><dt className="font-medium">Location:</dt><dd>{[expandedTx.city, expandedTx.state, expandedTx.country].filter(Boolean).join(", ") || "-"}</dd></div>
                <div className="flex gap-2"><dt className="font-medium">Service:</dt><dd>{expandedTx.service_id || "-"}</dd></div>
                {expandedTx.reviewed_by && (
                  <div className="flex gap-2"><dt className="font-medium">Reviewed by:</dt><dd>User {expandedTx.reviewed_by} at {expandedTx.reviewed_at ? new Date(expandedTx.reviewed_at).toLocaleString() : "-"}</dd></div>
                )}
              </dl>
            </div>
          </div>
        </div>
      )}

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="mt-4 flex items-center justify-between">
          <span className="text-sm text-gray-500">
            Page {page} of {totalPages} ({total} total)
          </span>
          <div className="flex gap-2">
            <button
              onClick={() => setPage((p) => Math.max(1, p - 1))}
              disabled={page <= 1}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Previous
            </button>
            <button
              onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
              disabled={page >= totalPages}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm text-gray-600 hover:bg-gray-50 disabled:opacity-40"
            >
              Next
            </button>
          </div>
        </div>
      )}

      {/* Modals */}
      {reclassifyTx && (
        <ReclassifyModal
          transaction={reclassifyTx}
          onClose={() => setReclassifyTx(null)}
        />
      )}
      {convertTx && (
        <ConvertToRuleModal
          transaction={convertTx}
          onClose={() => setConvertTx(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Badge Cell Renderers (AG Grid React components)
// ---------------------------------------------------------------------------

function ConfidenceCellRenderer(props) {
  if (!props.value) return <span>-</span>;
  const colors = {
    High: "bg-green-100 text-green-700",
    Medium: "bg-yellow-100 text-yellow-700",
    Low: "bg-red-100 text-red-700",
  };
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colors[props.value] || ""}`}>
      {props.value}
    </span>
  );
}

function StatusCellRenderer(props) {
  const colors = {
    Unreviewed: "bg-gray-100 text-gray-600",
    Approved: "bg-green-100 text-green-700",
    Reclassified: "bg-blue-100 text-blue-700",
    Flagged: "bg-red-100 text-red-700",
  };
  return (
    <span className={`inline-block rounded-full px-2 py-0.5 text-xs font-medium ${colors[props.value] || ""}`}>
      {props.value}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Actions Cell Renderer (AG Grid component)
// ---------------------------------------------------------------------------

function ActionsCellRenderer(props) {
  const { data: tx, onApprove, onReclassify, onFlag, onConvertToRule } = props;
  if (!tx) return null;

  return (
    <div className="flex gap-1 items-center h-full">
      {tx.review_status === "Unreviewed" && (
        <button
          onClick={() => onApprove(tx)}
          title="Approve"
          className="rounded p-1 text-green-600 hover:bg-green-50"
        >
          {"\u2713"}
        </button>
      )}
      <button
        onClick={() => onReclassify(tx)}
        title="Reclassify"
        className="rounded p-1 text-blue-600 hover:bg-blue-50"
      >
        {"\u270E"}
      </button>
      {tx.review_status !== "Flagged" && (
        <button
          onClick={() => onFlag(tx)}
          title="Flag"
          className="rounded p-1 text-red-600 hover:bg-red-50"
        >
          {"\u2691"}
        </button>
      )}
      <button
        onClick={() => onConvertToRule(tx)}
        title="Convert to Rule"
        className="rounded p-1 text-purple-600 hover:bg-purple-50"
      >
        {"\u21BB"}
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Staged File Card
// ---------------------------------------------------------------------------

function StagedFileCard({
  stagedFile,
  uploadResult,
  classifyResult,
  isUploading,
  isClassifying,
  uploadError,
  classifyError,
  onProcess,
  onClassify,
  onCancel,
}) {
  const isDone = !!classifyResult;
  const isUploaded = !!uploadResult;

  let borderColor = "border-amber-400";
  let bgColor = "bg-amber-50";
  if (isDone) {
    borderColor = "border-green-400";
    bgColor = "bg-green-50";
  } else if (isUploaded) {
    borderColor = "border-blue-400";
    bgColor = "bg-blue-50";
  }

  return (
    <div className={`mb-4 rounded-lg border-2 ${borderColor} ${bgColor} p-4 shadow-sm`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white text-lg shadow-sm">
            {isDone ? "\u2705" : isUploaded ? "\u2699\uFE0F" : "\uD83D\uDCC4"}
          </div>
          <div>
            <p className="font-semibold text-gray-800">{stagedFile.name}</p>
            <p className="text-xs text-gray-500">
              Dropped {stagedFile.timestamp.toLocaleString()}
            </p>
            {uploadResult && (
              <p className="mt-0.5 text-xs text-gray-600">
                {uploadResult.transactions_ingested} transactions ingested
                {uploadResult.transactions_skipped > 0 && (
                  <span className="text-amber-600">
                    {" "}({uploadResult.transactions_skipped} skipped)
                  </span>
                )}
              </p>
            )}
            {classifyResult && (
              <p className="mt-0.5 text-xs text-green-700">
                Classified: {classifyResult.classified_by_rule} by rule,{" "}
                {classifyResult.classified_by_llm} by LLM,{" "}
                {classifyResult.non_expense} non-expense,{" "}
                {classifyResult.unclassifiable} unclassifiable
              </p>
            )}
            {uploadError && (
              <p className="mt-0.5 text-xs text-red-600">
                Upload failed: {uploadError.message}
              </p>
            )}
            {classifyError && (
              <p className="mt-0.5 text-xs text-red-600">
                Classification failed: {classifyError.message}
              </p>
            )}
          </div>
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {!isUploaded && !isDone && (
            <button
              onClick={onProcess}
              disabled={isUploading}
              className="rounded-md bg-amber-500 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-amber-600 disabled:opacity-50"
            >
              {isUploading ? (
                <span className="flex items-center gap-1.5">
                  <Spinner /> Uploading...
                </span>
              ) : (
                "Process Transactions"
              )}
            </button>
          )}
          {isUploaded && !isDone && (
            <button
              onClick={onClassify}
              disabled={isClassifying}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 disabled:opacity-50"
            >
              {isClassifying ? (
                <span className="flex items-center gap-1.5">
                  <Spinner /> Classifying...
                </span>
              ) : (
                "Classify Transactions"
              )}
            </button>
          )}
          <button
            onClick={onCancel}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            {isDone ? "Dismiss" : "Cancel"}
          </button>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Tiny spinner
// ---------------------------------------------------------------------------

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
