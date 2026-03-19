import { useState } from "react";
import { useVendors, useConfirmVendor } from "../hooks/useVendors";

export default function VendorsPage() {
  const [search, setSearch] = useState("");
  const { data: vendors, isLoading } = useVendors(search || undefined);
  const confirm = useConfirmVendor();
  const [expandedId, setExpandedId] = useState(null);

  const pending = (vendors || []).filter((v) => v.status === "pending");

  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold text-gray-800">Vendors</h2>

      {pending.length > 0 && (
        <div className="mb-4 rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          {pending.length} vendor(s) pending confirmation.
        </div>
      )}

      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search vendors..."
          className="w-64 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div className="overflow-x-auto rounded-lg border border-gray-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-gray-200 bg-gray-50 text-xs font-medium uppercase tracking-wider text-gray-500">
              <th className="px-4 py-3">Vendor ID</th>
              <th className="px-4 py-3">Name</th>
              <th className="px-4 py-3">Status</th>
              <th className="px-4 py-3 text-right">Services</th>
              <th className="px-4 py-3 text-right">Transactions</th>
              <th className="px-4 py-3">Actions</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  Loading...
                </td>
              </tr>
            )}
            {!isLoading && (vendors || []).length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-8 text-center text-gray-400">
                  No vendors found.
                </td>
              </tr>
            )}
            {(vendors || []).map((v) => (
              <VendorRow
                key={v.vendor_id}
                vendor={v}
                isExpanded={expandedId === v.vendor_id}
                onToggle={() =>
                  setExpandedId(expandedId === v.vendor_id ? null : v.vendor_id)
                }
                onConfirm={() =>
                  confirm.mutate({
                    id: v.vendor_id,
                    data: { user_id: 1 },
                  })
                }
              />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function VendorRow({ vendor, isExpanded, onToggle, onConfirm }) {
  return (
    <>
      <tr
        onClick={onToggle}
        className="cursor-pointer transition hover:bg-gray-50"
      >
        <td className="whitespace-nowrap px-4 py-3 font-mono text-xs">
          {vendor.vendor_id}
        </td>
        <td className="px-4 py-3 font-medium">{vendor.vendor_name}</td>
        <td className="px-4 py-3">
          <span
            className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${
              vendor.status === "confirmed"
                ? "bg-green-100 text-green-800"
                : "bg-yellow-100 text-yellow-800"
            }`}
          >
            {vendor.status}
          </span>
        </td>
        <td className="px-4 py-3 text-right">
          {vendor.services?.length || 0}
        </td>
        <td className="px-4 py-3 text-right">{vendor.transaction_count}</td>
        <td
          className="whitespace-nowrap px-4 py-3"
          onClick={(e) => e.stopPropagation()}
        >
          {vendor.status === "pending" && (
            <button
              onClick={onConfirm}
              className="rounded-md bg-green-600 px-3 py-1 text-xs font-medium text-white hover:bg-green-700"
            >
              Confirm
            </button>
          )}
        </td>
      </tr>
      {isExpanded && vendor.services?.length > 0 && (
        <tr className="bg-gray-50">
          <td colSpan={6} className="px-8 py-4">
            <h4 className="mb-2 text-xs font-medium uppercase text-gray-500">
              Services
            </h4>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-gray-400">
                  <th className="pb-1 text-left">Service ID</th>
                  <th className="pb-1 text-left">Service Name</th>
                  <th className="pb-1 text-left">Status</th>
                </tr>
              </thead>
              <tbody>
                {vendor.services.map((s) => (
                  <tr key={s.service_id} className="text-gray-600">
                    <td className="py-0.5 font-mono">{s.service_id}</td>
                    <td className="py-0.5">{s.service_name}</td>
                    <td className="py-0.5">{s.status}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </td>
        </tr>
      )}
    </>
  );
}
