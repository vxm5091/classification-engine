import { useState } from "react";
import { useAcceptSuggestions, useReclassifyAll } from "../../hooks/useTransactions";

export default function RuleSuggestionsPanel({ suggestions, totalUnclassified, onClose }) {
  const [accepted, setAccepted] = useState({});
  const [editingSuggestion, setEditingSuggestion] = useState(null);
  const [editForm, setEditForm] = useState({});
  const [reclassifyResult, setReclassifyResult] = useState(null);
  const [createdCount, setCreatedCount] = useState(0);

  const acceptMutation = useAcceptSuggestions();
  const reclassifyMutation = useReclassifyAll();

  const acceptedCount = Object.values(accepted).filter(Boolean).length;

  function approveSingle(idx) {
    const s = suggestions[idx];
    const payload = {
      vendor_id: s.vendor_id,
      service_id: s.service_id || null,
      amount_min: s.amount_min || null,
      amount_max: s.amount_max || null,
      gl_code: s.gl_code,
      reasoning: s.reasoning || null,
    };
    acceptMutation.mutate(
      { suggestions: [payload], user_id: 1 },
      {
        onSuccess: () => {
          setAccepted((prev) => ({ ...prev, [idx]: true }));
          setCreatedCount((c) => c + 1);
        },
      }
    );
  }

  function approveAll() {
    const toAccept = suggestions
      .filter((_, idx) => !accepted[idx])
      .map((s) => ({
        vendor_id: s.vendor_id,
        service_id: s.service_id || null,
        amount_min: s.amount_min || null,
        amount_max: s.amount_max || null,
        gl_code: s.gl_code,
        reasoning: s.reasoning || null,
      }));
    if (toAccept.length === 0) return;
    acceptMutation.mutate(
      { suggestions: toAccept, user_id: 1 },
      {
        onSuccess: () => {
          const all = {};
          suggestions.forEach((_, idx) => { all[idx] = true; });
          setAccepted(all);
          setCreatedCount(suggestions.length);
        },
      }
    );
  }

  function handleEditApprove(idx, suggestion) {
    setEditingSuggestion({ idx, ...suggestion });
    setEditForm({
      vendor_id: suggestion.vendor_id || "",
      service_id: suggestion.service_id || "",
      amount_min: suggestion.amount_min ?? "",
      amount_max: suggestion.amount_max ?? "",
      gl_code: suggestion.gl_code || "",
    });
  }

  function setField(field) {
    return (e) => setEditForm((f) => ({ ...f, [field]: e.target.value }));
  }

  function confirmEdit(e) {
    e.preventDefault();
    if (!editingSuggestion) return;
    const idx = editingSuggestion.idx;
    const payload = {
      vendor_id: editForm.vendor_id || null,
      service_id: editForm.service_id || null,
      amount_min: editForm.amount_min ? Number(editForm.amount_min) : null,
      amount_max: editForm.amount_max ? Number(editForm.amount_max) : null,
      gl_code: Number(editForm.gl_code),
    };
    acceptMutation.mutate(
      { suggestions: [payload], user_id: 1 },
      {
        onSuccess: () => {
          setAccepted((prev) => ({
            ...prev,
            [idx]: { ...editingSuggestion, gl_code: Number(editForm.gl_code) },
          }));
          setCreatedCount((c) => c + 1);
          setEditingSuggestion(null);
        },
      }
    );
  }

  function handleReclassify() {
    reclassifyMutation.mutate(undefined, {
      onSuccess: (data) => {
        setReclassifyResult(data);
      },
    });
  }

  if (!suggestions || suggestions.length === 0) {
    return (
      <div className="mb-4 rounded-lg border-2 border-gray-300 bg-gray-50 p-6 text-center">
        <p className="text-gray-600">No rule suggestions available. All transactions either have matching rules or need manual classification.</p>
        <button
          onClick={onClose}
          className="mt-3 rounded-md border border-gray-300 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
        >
          Dismiss
        </button>
      </div>
    );
  }

  return (
    <div className="mb-4 rounded-lg border-2 border-indigo-300 bg-indigo-50/50 p-5 shadow-sm">
      {/* Header */}
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h3 className="text-lg font-semibold text-gray-800">
            {totalUnclassified} transaction{totalUnclassified !== 1 ? "s" : ""} could not be classified
          </h3>
          <p className="mt-0.5 text-sm text-gray-500">
            Review the suggested rules below. Approve to create rules, then re-classify.
          </p>
        </div>
        <button
          onClick={onClose}
          className="text-gray-400 hover:text-gray-600"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Suggestion cards */}
      <div className="space-y-3">
        {suggestions.map((s, idx) => {
          const isAccepted = !!accepted[idx];
          return (
            <div
              key={idx}
              className={`rounded-lg border p-4 transition-colors ${
                isAccepted
                  ? "border-green-300 bg-green-50/50"
                  : "border-gray-200 bg-white"
              }`}
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-gray-800">{s.vendor_name}</span>
                    {s.service_name && (
                      <span className="rounded bg-gray-100 px-2 py-0.5 text-xs text-gray-600">
                        {s.service_name}
                      </span>
                    )}
                    <span className="text-gray-400">{"\u2192"}</span>
                    <span className="rounded bg-blue-100 px-2 py-0.5 text-sm font-medium text-blue-700">
                      GL {typeof accepted[idx] === "object" ? accepted[idx].gl_code : s.gl_code}
                      {s.gl_class && ` (${s.gl_class})`}
                    </span>
                  </div>
                  {(s.amount_min != null || s.amount_max != null) && (
                    <p className="mt-1 text-xs text-gray-500">
                      Amount range: {s.amount_min != null ? `$${s.amount_min}` : "any"} – {s.amount_max != null ? `$${s.amount_max}` : "any"}
                    </p>
                  )}
                  <p className="mt-2 text-sm text-gray-600">{s.reasoning}</p>
                  <p className="mt-1 text-xs text-gray-400">
                    Affects {s.affected_count} transaction{s.affected_count !== 1 ? "s" : ""}
                    {s.affected_transaction_ids?.length > 0 && (
                      <span className="ml-1">
                        ({s.affected_transaction_ids.slice(0, 5).join(", ")}
                        {s.affected_transaction_ids.length > 5 && ", ..."})
                      </span>
                    )}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  {isAccepted ? (
                    <span className="rounded-md border border-green-300 bg-green-100 px-3 py-1.5 text-xs font-medium text-green-700">
                      {"\u2713"} Rule Created
                    </span>
                  ) : (
                    <>
                      <button
                        onClick={() => approveSingle(idx)}
                        disabled={acceptMutation.isPending}
                        className="rounded-md border border-green-300 bg-white px-3 py-1.5 text-xs font-medium text-green-700 hover:bg-green-50 disabled:opacity-50"
                      >
                        Approve
                      </button>
                      <button
                        onClick={() => handleEditApprove(idx, s)}
                        disabled={acceptMutation.isPending}
                        className="rounded-md border border-blue-300 bg-white px-3 py-1.5 text-xs font-medium text-blue-700 hover:bg-blue-50 disabled:opacity-50"
                      >
                        Edit & Approve
                      </button>
                    </>
                  )}
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer actions */}
      <div className="mt-4 flex items-center justify-between border-t border-indigo-200 pt-4">
        <div className="text-sm text-gray-500">
          {acceptedCount} of {suggestions.length} rule{suggestions.length !== 1 ? "s" : ""} created
        </div>
        <div className="flex gap-2">
          <button
            onClick={approveAll}
            disabled={acceptedCount === suggestions.length || acceptMutation.isPending}
            className="rounded-md border border-indigo-300 bg-white px-4 py-2 text-sm font-medium text-indigo-700 hover:bg-indigo-50 disabled:opacity-40"
          >
            {acceptMutation.isPending ? (
              <span className="flex items-center gap-1.5">
                <Spinner /> Creating...
              </span>
            ) : (
              "Approve All"
            )}
          </button>

          {reclassifyResult && typeof reclassifyResult === "object" ? (
            <div className="rounded-md bg-green-100 px-4 py-2 text-sm text-green-700">
              {reclassifyResult.newly_classified} newly classified, {reclassifyResult.still_unclassified} still unmatched
            </div>
          ) : (
            <button
              onClick={handleReclassify}
              disabled={createdCount === 0 || reclassifyMutation.isPending}
              className="rounded-md bg-green-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-green-700 disabled:opacity-50"
            >
              {reclassifyMutation.isPending ? (
                <span className="flex items-center gap-1.5">
                  <Spinner /> Re-classifying...
                </span>
              ) : (
                "Re-classify Transactions"
              )}
            </button>
          )}

          <button
            onClick={onClose}
            className="rounded-md border border-gray-300 bg-white px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
          >
            Dismiss
          </button>
        </div>
      </div>

      {/* Edit modal — full rule form */}
      {editingSuggestion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
          <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
            <h2 className="mb-1 text-lg font-semibold text-gray-800">Edit & Create Rule</h2>
            <p className="mb-4 text-xs text-gray-500">
              {editingSuggestion.vendor_name}
              {editingSuggestion.reasoning && ` — ${editingSuggestion.reasoning}`}
            </p>
            <form onSubmit={confirmEdit} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Vendor ID</label>
                  <input value={editForm.vendor_id} onChange={setField("vendor_id")} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Service ID</label>
                  <input value={editForm.service_id} onChange={setField("service_id")} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Amount Min</label>
                  <input type="number" step="0.01" value={editForm.amount_min} onChange={setField("amount_min")} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
                </div>
                <div>
                  <label className="mb-1 block text-sm font-medium text-gray-700">Amount Max</label>
                  <input type="number" step="0.01" value={editForm.amount_max} onChange={setField("amount_max")} className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
                </div>
              </div>
              <div>
                <label className="mb-1 block text-sm font-medium text-gray-700">GL Code</label>
                <input type="number" value={editForm.gl_code} onChange={setField("gl_code")} required className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none" />
              </div>
              <div className="flex justify-end gap-3">
                <button type="button" onClick={() => setEditingSuggestion(null)} className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50">Cancel</button>
                <button type="submit" disabled={acceptMutation.isPending} className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50">
                  {acceptMutation.isPending ? "Creating..." : "Create Rule"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

function Spinner() {
  return (
    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z" />
    </svg>
  );
}
