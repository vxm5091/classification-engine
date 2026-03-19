import { useState } from "react";
import { useConvertToRule } from "../../hooks/useTransactions";

export default function ConvertToRuleModal({ transaction, onClose }) {
  const [form, setForm] = useState({
    vendor_id: transaction.vendor_id || "",
    service_id: transaction.service_id || "",
    amount_min: transaction.amount || "",
    amount_max: transaction.amount || "",
    gl_code: transaction.gl_code || "",
  });
  const convert = useConvertToRule();

  function set(field) {
    return (e) => setForm((f) => ({ ...f, [field]: e.target.value }));
  }

  function handleSubmit(e) {
    e.preventDefault();
    const body = {
      vendor_id: form.vendor_id || null,
      service_id: form.service_id || null,
      amount_min: form.amount_min ? Number(form.amount_min) : null,
      amount_max: form.amount_max ? Number(form.amount_max) : null,
      gl_code: Number(form.gl_code),
      user_id: 1,
    };
    convert.mutate({ id: transaction.transaction_id, data: body }, { onSuccess: onClose });
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          Convert to Rule
        </h2>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Vendor ID
              </label>
              <input
                value={form.vendor_id}
                onChange={set("vendor_id")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Service ID
              </label>
              <input
                value={form.service_id}
                onChange={set("service_id")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Amount Min
              </label>
              <input
                type="number"
                step="0.01"
                value={form.amount_min}
                onChange={set("amount_min")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Amount Max
              </label>
              <input
                type="number"
                step="0.01"
                value={form.amount_max}
                onChange={set("amount_max")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium text-gray-700">
              GL Code
            </label>
            <input
              type="number"
              value={form.gl_code}
              onChange={set("gl_code")}
              required
              className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
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
              disabled={convert.isPending}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {convert.isPending ? "Creating..." : "Create Rule"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
