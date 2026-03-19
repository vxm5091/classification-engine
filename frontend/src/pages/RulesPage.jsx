import { useState } from "react";
import {
  useRules,
  useCreateRule,
  useUpdateRule,
  useDeactivateRule,
} from "../hooks/useRules";

export default function RulesPage() {
  const { data: rules, isLoading } = useRules();
  const [modalMode, setModalMode] = useState(null); // 'create' | 'edit'
  const [editingRule, setEditingRule] = useState(null);

  function openCreate() {
    setEditingRule(null);
    setModalMode("create");
  }

  function openEdit(rule) {
    setEditingRule(rule);
    setModalMode("edit");
  }

  return (
    <div>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-xl font-semibold text-gray-800">
          Classification Rules
        </h2>
        <button
          onClick={openCreate}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          + Create Rule
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-xs font-medium uppercase tracking-wider text-gray-500">
              <th className="px-4 py-3">Rule ID</th>
              <th className="px-4 py-3">Vendor</th>
              <th className="px-4 py-3">Service</th>
              <th className="px-4 py-3">Amount Range</th>
              <th className="px-4 py-3">GL Code</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Match Count</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  Loading...
                </td>
              </tr>
            )}
            {!isLoading && (rules || []).length === 0 && (
              <tr>
                <td colSpan={8} className="px-4 py-8 text-center text-gray-400">
                  No rules found.
                </td>
              </tr>
            )}
            {(rules || []).map((rule) => (
              <RuleRow
                key={rule.rule_id}
                rule={rule}
                onEdit={() => openEdit(rule)}
              />
            ))}
          </tbody>
        </table>
      </div>

      {modalMode && (
        <RuleFormModal
          mode={modalMode}
          rule={editingRule}
          onClose={() => setModalMode(null)}
        />
      )}
    </div>
  );
}

function RuleRow({ rule, onEdit }) {
  const deactivate = useDeactivateRule();

  const amountRange =
    rule.amount_min != null || rule.amount_max != null
      ? `$${rule.amount_min ?? "0"} - $${rule.amount_max ?? "\u221E"}`
      : "-";

  return (
    <tr className="transition hover:bg-gray-50">
      <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
        {rule.rule_id}
      </td>
      <td className="px-4 py-3">{rule.vendor_id || "-"}</td>
      <td className="px-4 py-3">{rule.service_id || "-"}</td>
      <td className="px-4 py-3 text-xs">{amountRange}</td>
      <td className="px-4 py-3">{rule.gl_code}</td>
      <td className="px-4 py-3">
        <span
          className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
            rule.is_active
              ? "bg-green-100 text-green-800"
              : "bg-gray-100 text-gray-500"
          }`}
        >
          {rule.is_active ? "Active" : "Inactive"}
        </span>
      </td>
      <td className="px-4 py-3 text-right font-mono">{rule.match_count}</td>
      <td className="whitespace-nowrap px-4 py-3">
        <div className="flex gap-2">
          <button
            onClick={onEdit}
            className="text-xs text-blue-600 hover:underline"
          >
            Edit
          </button>
          {rule.is_active && (
            <button
              onClick={() => deactivate.mutate(rule.rule_id)}
              className="text-xs text-red-600 hover:underline"
            >
              Deactivate
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}

function RuleFormModal({ mode, rule, onClose }) {
  const [form, setForm] = useState({
    vendor_id: rule?.vendor_id || "",
    service_id: rule?.service_id || "",
    amount_min: rule?.amount_min || "",
    amount_max: rule?.amount_max || "",
    time_of_month_start: rule?.time_of_month_start || "",
    time_of_month_end: rule?.time_of_month_end || "",
    gl_code: rule?.gl_code || "",
    is_active: rule?.is_active ?? true,
  });

  const create = useCreateRule();
  const update = useUpdateRule();

  function set(field) {
    return (e) => {
      const val =
        e.target.type === "checkbox" ? e.target.checked : e.target.value;
      setForm((f) => ({ ...f, [field]: val }));
    };
  }

  function handleSubmit(e) {
    e.preventDefault();
    const body = {
      vendor_id: form.vendor_id || null,
      service_id: form.service_id || null,
      amount_min: form.amount_min ? Number(form.amount_min) : null,
      amount_max: form.amount_max ? Number(form.amount_max) : null,
      time_of_month_start: form.time_of_month_start
        ? Number(form.time_of_month_start)
        : null,
      time_of_month_end: form.time_of_month_end
        ? Number(form.time_of_month_end)
        : null,
      gl_code: Number(form.gl_code),
    };

    if (mode === "create") {
      body.user_id = 1;
      create.mutate(body, { onSuccess: onClose });
    } else {
      body.is_active = form.is_active;
      update.mutate({ id: rule.rule_id, data: body }, { onSuccess: onClose });
    }
  }

  const isPending = create.isPending || update.isPending;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="w-full max-w-lg rounded-lg bg-white p-6 shadow-xl">
        <h2 className="mb-4 text-lg font-semibold text-gray-800">
          {mode === "create" ? "Create Rule" : "Edit Rule"}
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

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Day of Month Start
              </label>
              <input
                type="number"
                min="1"
                max="31"
                value={form.time_of_month_start}
                onChange={set("time_of_month_start")}
                className="w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="mb-1 block text-sm font-medium text-gray-700">
                Day of Month End
              </label>
              <input
                type="number"
                min="1"
                max="31"
                value={form.time_of_month_end}
                onChange={set("time_of_month_end")}
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

          {mode === "edit" && (
            <label className="flex items-center gap-2 text-sm text-gray-700">
              <input
                type="checkbox"
                checked={form.is_active}
                onChange={set("is_active")}
                className="rounded border-gray-300"
              />
              Active
            </label>
          )}

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
              disabled={isPending}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
            >
              {isPending ? "Saving..." : mode === "create" ? "Create" : "Save"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
