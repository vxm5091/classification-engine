import { useState, useMemo, useCallback, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { AgGridReact } from "ag-grid-react";
import { AllCommunityModule, ModuleRegistry, themeAlpine } from "ag-grid-community";
import { getGLCodes, getBatches, uploadCSV, triggerClassify } from "../api/client";
import {
  useTransactions,
  useApproveTransaction,
  useFlagTransaction,
  useSuggestRules,
  useReclassifyAll,
  useReclassifySingle,
  useStats,
} from "../hooks/useTransactions";
import { ConfidenceBadge, ReviewBadge } from "../components/shared/Badge";
import StatsBar from "../components/shared/StatsBar";
import ReclassifyModal from "../components/transactions/ReclassifyModal";
import ConvertToRuleModal from "../components/transactions/ConvertToRuleModal";
import RuleSuggestionsPanel from "../components/transactions/RuleSuggestionsPanel";

ModuleRegistry.registerModules([AllCommunityModule]);

const gridTheme = themeAlpine.withParams({
  fontSize: 12,
  rowHeight: 36,
  headerHeight: 38,
  cellTextColor: "#374151",
});
const PAGE_SIZE = 50;

export default function TransactionsPage() {
  const queryClient = useQueryClient();
  const gridRef = useRef(null);
  const detailPanelRef = useRef(null);
  const [page, setPage] = useState(1);
  const [sortBy, setSortBy] = useState("confidence");
  const [sortOrder, setSortOrder] = useState("asc");
  const [filters, setFilters] = useState({
    review_status: "",
    confidence: "",
    gl_code: "",
    vendor_search: "",
    upload_batch: "",
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

  // --- Rule suggestions state ---
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [suggestionsData, setSuggestionsData] = useState(null);
  const suggestMutation = useSuggestRules();

  const uploadMutation = useMutation({
    mutationFn: (file) => uploadCSV(file),
    onSuccess: (data) => {
      setUploadResult(data);
      queryClient.invalidateQueries({ queryKey: ["transactions"] });
      queryClient.invalidateQueries({ queryKey: ["stats"] });
      queryClient.invalidateQueries({ queryKey: ["batches"] });
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
      setSuggestionsData(null);
      setShowSuggestions(false);
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
  function handleSuggestRules() {
    suggestMutation.mutate(undefined, {
      onSuccess: (data) => {
        setSuggestionsData(data);
        setShowSuggestions(true);
      },
    });
  }
  function handleCancel() {
    setStagedFile(null);
    setUploadResult(null);
    setClassifyResult(null);
    setSuggestionsData(null);
    setShowSuggestions(false);
  }

  // --- Data fetching ---
  const params = useMemo(() => {
    const p = { page, page_size: PAGE_SIZE, sort_by: sortBy, sort_order: sortOrder };
    if (filters.review_status) p.review_status = filters.review_status;
    if (filters.confidence) p.confidence = filters.confidence;
    if (filters.gl_code) p.gl_code = filters.gl_code;
    if (filters.vendor_search) p.vendor_search = filters.vendor_search;
    if (filters.upload_batch) p.upload_batch = filters.upload_batch;
    if (filters.date_from) p.date_from = filters.date_from;
    if (filters.date_to) p.date_to = filters.date_to;
    return p;
  }, [page, sortBy, sortOrder, filters]);

  const { data, isLoading } = useTransactions(params);
  const { data: glCodes } = useQuery({
    queryKey: ["glCodes", 3],
    queryFn: () => getGLCodes(3),
  });
  const { data: batches } = useQuery({
    queryKey: ["batches"],
    queryFn: getBatches,
  });
  const { data: statsData } = useStats();

  const approve = useApproveTransaction();
  const flag = useFlagTransaction();
  const reclassifyAllMutation = useReclassifyAll();
  const reclassifySingleMutation = useReclassifySingle();

  useEffect(() => {
    if (expandedTx && detailPanelRef.current) {
      detailPanelRef.current.scrollIntoView({ behavior: "smooth", block: "nearest" });
    }
  }, [expandedTx]);

  function updateFilter(field, value) {
    setFilters((f) => ({ ...f, [field]: value }));
    setPage(1);
  }

  const transactions = data?.transactions || [];
  const total = data?.total || 0;
  const totalPages = Math.ceil(total / PAGE_SIZE);

  const unclassifiedCount = statsData?.by_method?.Unclassified || 0;

  useEffect(() => {
    if (expandedTx && transactions.length > 0) {
      const updated = transactions.find(
        (t) => t.transaction_id === expandedTx.transaction_id
      );
      if (updated && updated.id !== expandedTx.id) {
        setExpandedTx(updated);
      }
    }
  }, [transactions]);

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
        minWidth: 100,
        sortable: true,
      },
      {
        headerName: "Description",
        field: "raw_description",
        flex: 1,
        minWidth: 200,
        sortable: true,
        tooltipField: "raw_description",
      },
      {
        headerName: "Amount",
        field: "amount",
        minWidth: 100,
        sortable: true,
        type: "rightAligned",
        valueFormatter: (p) => formatAmount(p.value),
        cellClass: "font-mono",
      },
      {
        headerName: "Vendor",
        field: "vendor_id",
        minWidth: 150,
        sortable: true,
        cellRenderer: VendorCellRenderer,
      },
      {
        headerName: "GL Code",
        field: "gl_code",
        minWidth: 100,
        sortable: true,
        cellRenderer: GLCodeCellRenderer,
      },
      {
        headerName: "Confidence",
        field: "confidence",
        minWidth: 90,
        sortable: true,
        sort: "asc",
        cellRenderer: ConfidenceCellRenderer,
      },
      {
        headerName: "Method",
        field: "method",
        minWidth: 110,
        sortable: true,
        cellRenderer: MethodCellRenderer,
      },
      {
        headerName: "Status",
        field: "review_status",
        minWidth: 100,
        sortable: true,
        cellRenderer: StatusCellRenderer,
      },
      {
        headerName: "Actions",
        field: "actions",
        width: 160,
        sortable: false,
        suppressAutoSize: true,
        cellRenderer: ActionsCellRenderer,
        cellRendererParams: {
          onApprove: (tx) =>
            approve.mutate({ id: tx.transaction_id, data: { user_id: 1 } }),
          onReclassify: (tx) => setReclassifyTx(tx),
          onReclassifySingle: (tx) =>
            reclassifySingleMutation.mutate(tx.transaction_id),
          onFlag: (tx) =>
            flag.mutate({ id: tx.transaction_id, data: { user_id: 1 } }),
          onConvertToRule: (tx) => setConvertTx(tx),
        },
      },
    ],
    [approve, flag, reclassifySingleMutation]
  );

  const defaultColDef = useMemo(
    () => ({
      resizable: true,
      suppressMovable: true,
      comparator: () => 0,
    }),
    []
  );

  const autoSizeStrategy = useMemo(() => ({
    type: "fitGridWidth",
    defaultMinWidth: 80,
  }), []);

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
      if (prev?.transaction_id === tx.transaction_id) {
        event.api.deselectAll();
        return null;
      }
      event.node.setSelected(true, true);
      return tx;
    });
  }, []);

  const handleOutsideClick = useCallback((e) => {
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
          isSuggesting={suggestMutation.isPending}
          uploadError={uploadMutation.error}
          classifyError={classifyMutation.error}
          onProcess={handleProcess}
          onClassify={handleClassify}
          onSuggestRules={handleSuggestRules}
          onCancel={handleCancel}
        />
      )}

      {/* Rule suggestions panel */}
      {showSuggestions && suggestionsData && (
        <RuleSuggestionsPanel
          suggestions={suggestionsData.suggestions}
          totalUnclassified={suggestionsData.total_unclassified}
          onClose={() => {
            setShowSuggestions(false);
            queryClient.invalidateQueries({ queryKey: ["transactions"] });
            queryClient.invalidateQueries({ queryKey: ["stats"] });
          }}
        />
      )}

      {/* Unclassified transactions banner */}
      {!showSuggestions && unclassifiedCount > 0 && (
        <div className="mb-4 flex items-center justify-between rounded-lg border border-amber-300 bg-amber-50 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="text-amber-600 text-lg">{"\u26A0"}</span>
            <span className="text-sm font-medium text-amber-800">
              {unclassifiedCount} transaction{unclassifiedCount !== 1 ? "s" : ""} need rules
            </span>
          </div>
          <button
            onClick={handleSuggestRules}
            disabled={suggestMutation.isPending}
            className="rounded-md bg-amber-500 px-4 py-1.5 text-sm font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            {suggestMutation.isPending ? (
              <span className="flex items-center gap-1.5">
                <Spinner /> Generating...
              </span>
            ) : (
              "Suggest Rules"
            )}
          </button>
        </div>
      )}

      <StatsBar />

      {/* Filters */}
      <div className="mb-4 flex flex-wrap items-end gap-3 rounded-lg border border-gray-200 bg-white p-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-gray-500">
            Batch
          </label>
          <select
            value={filters.upload_batch}
            onChange={(e) => updateFilter("upload_batch", e.target.value)}
            className="rounded-md border border-gray-300 px-2 py-1.5 text-sm focus:border-blue-500 focus:outline-none"
          >
            <option value="">All Batches</option>
            {(batches || []).map((b) => (
              <option key={b} value={b}>
                {b}
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

      {/* Table toolbar */}
      <div className="mb-2 flex items-center justify-between">
        <div className="text-sm text-gray-500">
          {total} transaction{total !== 1 ? "s" : ""}
        </div>
        {unclassifiedCount > 0 && (
          <button
            onClick={() => reclassifyAllMutation.mutate()}
            disabled={reclassifyAllMutation.isPending}
            className="inline-flex items-center gap-1.5 rounded-md bg-amber-500 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-600 disabled:opacity-50"
          >
            <span className={reclassifyAllMutation.isPending ? "animate-spin" : ""}>&#x21BB;</span>
            {reclassifyAllMutation.isPending
              ? "Reclassifying..."
              : `Reclassify ${unclassifiedCount} Unclassified`}
          </button>
        )}
      </div>

      {/* AG Grid Table */}
      <div className="rounded-lg border border-gray-200" style={{ width: "100%", height: 600 }}>
        <AgGridReact
          ref={gridRef}
          theme={gridTheme}
          rowData={transactions}
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          autoSizeStrategy={autoSizeStrategy}
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
        <div ref={detailPanelRef} data-detail-panel className="mt-2 rounded-lg border border-blue-200 bg-blue-50/30 p-4">
          <div className="flex items-center justify-between mb-3">
            <div>
              <h3 className="font-semibold text-gray-800">
                {expandedTx.raw_description}
              </h3>
              <p className="text-xs text-gray-400 mt-0.5">
                {expandedTx.transaction_id} &middot; v{expandedTx.version}
                {expandedTx.upload_batch && <span> &middot; {expandedTx.upload_batch}</span>}
              </p>
            </div>
            <button
              onClick={() => setExpandedTx(null)}
              className="text-gray-400 hover:text-gray-600 text-sm"
            >
              Close
            </button>
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <h4 className="mb-1 font-medium text-gray-700">Details</h4>
              <dl className="space-y-1.5 text-xs">
                <DetailRow label="Date" value={expandedTx.date ? new Date(expandedTx.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" }) : "-"} />
                <DetailRow label="Amount" value={formatAmount(expandedTx.amount)} />
                <DetailRow label="Vendor" value={expandedTx.vendor_id ? `${expandedTx.vendor_id}${expandedTx.vendor_name ? ` — ${expandedTx.vendor_name}` : ""}` : "-"} />
                <DetailRow label="Service" value={expandedTx.service_id || "-"} />
                <DetailRow label="Location" value={[expandedTx.city, expandedTx.state, expandedTx.country].filter(Boolean).join(", ") || "-"} />
                <div className="border-t border-blue-100 pt-1.5" />
                <DetailRow label="GL Code" value={expandedTx.gl_code ? `${expandedTx.gl_code}${expandedTx.gl_class ? ` — ${expandedTx.gl_class}` : ""}` : "Unclassified"} />
                <DetailRow label="Confidence" value={expandedTx.confidence || "-"} />
                <DetailRow label="Method" value={expandedTx.method || "-"} />
                <DetailRow label="Status" value={expandedTx.review_status} />
                <DetailRow label="Rule ID" value={expandedTx.rule_id != null ? `R-${expandedTx.rule_id}` : "-"} />
                {expandedTx.reviewed_by && (
                  <DetailRow label="Reviewed by" value={`User ${expandedTx.reviewed_by} at ${expandedTx.reviewed_at ? new Date(expandedTx.reviewed_at).toLocaleString() : "-"}`} />
                )}
              </dl>

              {(expandedTx.review_status === "Unreviewed" || expandedTx.review_status === "Flagged") && (
                <div className="mt-3 flex gap-2">
                  <button
                    onClick={() => approve.mutate({ id: expandedTx.transaction_id, data: { user_id: 1 } })}
                    className="rounded-md bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
                  >
                    Approve
                  </button>
                  <button
                    onClick={() => setReclassifyTx(expandedTx)}
                    className="rounded-md bg-blue-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-blue-700"
                  >
                    Reclassify
                  </button>
                </div>
              )}
            </div>
            <div>
              <h4 className="mb-1 font-medium text-gray-700">Classification Reasoning</h4>
              <ReasoningBlock reasoning={expandedTx.reasoning} />
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
// Cell Renderers
// ---------------------------------------------------------------------------

function ReasoningBlock({ reasoning }) {
  if (!reasoning) {
    return <p className="text-gray-400 text-xs">No reasoning available.</p>;
  }

  const sections = [];
  let remaining = reasoning;

  const justificationSplit = remaining.split("\n\nRule Justification:");
  if (justificationSplit.length > 1) {
    remaining = justificationSplit[0];
    sections.push({
      type: "justification",
      label: "LLM Rule Justification",
      text: justificationSplit[1].trim(),
    });
  }

  const advisorySplit = remaining.split("\n\nLLM Advisory:");
  if (advisorySplit.length > 1) {
    remaining = advisorySplit[0];
    sections.push({
      type: "advisory",
      label: "LLM Advisory",
      text: advisorySplit[1].trim(),
    });
  }

  return (
    <div className="space-y-2">
      <p className="text-gray-600 text-xs leading-relaxed">{remaining}</p>
      {sections.map((s, i) => (
        <div
          key={i}
          className={`rounded-md border p-3 ${
            s.type === "justification"
              ? "border-indigo-200 bg-indigo-50"
              : "border-sky-200 bg-sky-50"
          }`}
        >
          <p className={`text-xs font-medium mb-1 ${
            s.type === "justification" ? "text-indigo-700" : "text-sky-700"
          }`}>{s.label}</p>
          <p className={`text-xs leading-relaxed ${
            s.type === "justification" ? "text-indigo-800" : "text-sky-800"
          }`}>{s.text}</p>
        </div>
      ))}
    </div>
  );
}

function DetailRow({ label, value }) {
  return (
    <div className="flex gap-2">
      <dt className="font-medium text-gray-500 shrink-0 w-20">{label}</dt>
      <dd className="text-gray-700">{value}</dd>
    </div>
  );
}

function VendorCellRenderer(props) {
  const tx = props.data;
  if (!tx.vendor_id) return <span className="text-gray-400">{"\u2014"}</span>;
  return (
    <span>
      {tx.vendor_id}
      {tx.service_id && <span className="text-gray-400 ml-1">/ {tx.service_id}</span>}
    </span>
  );
}

function GLCodeCellRenderer(props) {
  if (!props.data.gl_code) {
    if (props.data.method === "Unclassified") {
      return (
        <span className="inline-block rounded-full bg-orange-100 px-2 py-0.5 text-xs font-medium text-orange-700">
          Unclassified
        </span>
      );
    }
    return <span className="text-gray-400">{"\u2014"}</span>;
  }
  const cls = props.data.gl_class ? ` (${props.data.gl_class})` : "";
  return <span>{props.data.gl_code}{cls}</span>;
}

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

function MethodCellRenderer(props) {
  if (!props.value) return <span className="text-gray-400">-</span>;
  const colors = {
    "Rule Match": "text-gray-600",
    "LLM Inference": "text-purple-500",
    "Pre-classified": "text-blue-500",
    "Unclassified": "text-orange-600 font-medium",
    "Unclassifiable": "text-gray-400",
    "Manual": "text-green-600",
  };
  return (
    <span className={`text-xs ${colors[props.value] || "text-gray-500"}`}>
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
// Actions Cell Renderer
// ---------------------------------------------------------------------------

function ActionsCellRenderer(props) {
  const { data: tx, onApprove, onReclassify, onReclassifySingle, onFlag, onConvertToRule } = props;
  if (!tx) return null;

  return (
    <div className="flex gap-1 items-center h-full">
      {(tx.review_status === "Unreviewed" || tx.review_status === "Flagged") && (
        <button
          onClick={(e) => { e.stopPropagation(); onApprove(tx); }}
          title="Approve"
          className="rounded p-1 text-green-600 hover:bg-green-50"
        >
          {"\u2713"}
        </button>
      )}
      <button
        onClick={(e) => { e.stopPropagation(); onReclassifySingle(tx); }}
        title="Re-run classification"
        className="rounded p-1 text-amber-600 hover:bg-amber-50"
      >
        {"\u21BB"}
      </button>
      <button
        onClick={(e) => { e.stopPropagation(); onReclassify(tx); }}
        title="Manual reclassify"
        className="rounded p-1 text-blue-600 hover:bg-blue-50"
      >
        {"\u270E"}
      </button>
      {tx.review_status !== "Flagged" && (
        <button
          onClick={(e) => { e.stopPropagation(); onFlag(tx); }}
          title="Flag"
          className="rounded p-1 text-red-600 hover:bg-red-50"
        >
          {"\u2691"}
        </button>
      )}
      <button
        onClick={(e) => { e.stopPropagation(); onConvertToRule(tx); }}
        title="Convert to Rule"
        className="rounded p-1 text-purple-600 hover:bg-purple-50"
      >
        {"\u2696"}
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
  isSuggesting,
  uploadError,
  classifyError,
  onProcess,
  onClassify,
  onSuggestRules,
  onCancel,
}) {
  const isDone = !!classifyResult;
  const isUploaded = !!uploadResult;
  const hasUnclassified = classifyResult?.unclassified > 0;

  let borderColor = "border-amber-400";
  let bgColor = "bg-amber-50";
  if (isDone && !hasUnclassified) {
    borderColor = "border-green-400";
    bgColor = "bg-green-50";
  } else if (isDone && hasUnclassified) {
    borderColor = "border-blue-400";
    bgColor = "bg-blue-50";
  } else if (isUploaded) {
    borderColor = "border-blue-400";
    bgColor = "bg-blue-50";
  }

  return (
    <div className={`mb-4 rounded-lg border-2 ${borderColor} ${bgColor} p-4 shadow-sm`}>
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-white text-lg shadow-sm">
            {isDone && !hasUnclassified ? "\u2705" : isUploaded ? "\u2699\uFE0F" : "\uD83D\uDCC4"}
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
              <div className="mt-1 flex flex-wrap gap-2 text-xs">
                {classifyResult.pre_classified > 0 && (
                  <span className="rounded bg-blue-100 px-1.5 py-0.5 text-blue-700">
                    {classifyResult.pre_classified} pre-classified
                  </span>
                )}
                {classifyResult.classified_by_rule > 0 && (
                  <span className="rounded bg-green-100 px-1.5 py-0.5 text-green-700">
                    {classifyResult.classified_by_rule} by rule
                  </span>
                )}
                {classifyResult.medium_confidence > 0 && (
                  <span className="rounded bg-yellow-100 px-1.5 py-0.5 text-yellow-700">
                    {classifyResult.medium_confidence} conflicts (Medium)
                  </span>
                )}
                {classifyResult.unclassified > 0 && (
                  <span className="rounded bg-red-100 px-1.5 py-0.5 text-red-700">
                    {classifyResult.unclassified} unclassified
                  </span>
                )}
                {classifyResult.non_expense > 0 && (
                  <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-600">
                    {classifyResult.non_expense} non-expense
                  </span>
                )}
              </div>
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
          {isDone && hasUnclassified && (
            <button
              onClick={onSuggestRules}
              disabled={isSuggesting}
              className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-indigo-700 disabled:opacity-50"
            >
              {isSuggesting ? (
                <span className="flex items-center gap-1.5">
                  <Spinner /> Generating...
                </span>
              ) : (
                `Suggest Rules for ${classifyResult.unclassified} unclassified`
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
