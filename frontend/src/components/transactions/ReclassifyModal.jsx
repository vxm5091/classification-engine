import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getGLHierarchy } from "../../api/client";
import { useReclassifyTransaction } from "../../hooks/useTransactions";

export default function ReclassifyModal({ transaction, onClose }) {
  const [glCode, setGlCode] = useState(transaction.gl_code || "");
  const [notes, setNotes] = useState("");
  const { data: hierarchy } = useQuery({
    queryKey: ["glHierarchy"],
    queryFn: getGLHierarchy,
  });
  const reclassify = useReclassifyTransaction();

  function handleSubmit(e) {
    e.preventDefault();
    reclassify.mutate(
      { id: transaction.transaction_id, data: { gl_code: Number(glCode), user_id: 1, notes } },
      { onSuccess: onClose },
    );
  }

  function renderOptions(nodes, depth = 0) {
    const opts = [];
    for (const node of nodes || []) {
      opts.push(
        <option key={node.gl_code} value={node.gl_code}>
          {"\u00A0".repeat(depth * 4)}
          {node.gl_code} - {node.description || node.gl_class}
        </option>,
      );
      if (node.children?.length) {
        opts.push(...renderOptions(node.children, depth + 1));
      }
    }
    return opts;
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Reclassify Transaction
        </h2>

        <p className="mb-1 text-sm text-gray-500">
          Current GL Code:{" "}
          <span className="font-medium text-gray-700">
            {transaction.gl_code ?? "None"}
          </span>
        </p>
        <p className="mb-4 text-sm text-gray-500 truncate">
          {transaction.raw_description}
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              New GL Code
            </label>
            <select
              value={glCode}
              onChange={(e) => setGlCode(e.target.value)}
              required
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            >
              <option value="">Select GL Code...</option>
              {renderOptions(hierarchy)}
            </select>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              Notes
            </label>
            <textarea
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="Reason for reclassification..."
            />
          </div>

          <div className="flex justify-end gap-3">
            <button
              type="button"
              onClick={onClose}
              className="rounded-md border border-gray-300 px-4 py-2 text-sm text-gray-600 hover:bg-gray-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={reclassify.isPending}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {reclassify.isPending ? "Saving..." : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
