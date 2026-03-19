import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { getGLHierarchy } from "../api/client";

export default function GLReferencePage() {
  const { data: hierarchy, isLoading } = useQuery({
    queryKey: ["glHierarchy"],
    queryFn: getGLHierarchy,
  });
  const [search, setSearch] = useState("");
  const [expandedCodes, setExpandedCodes] = useState(new Set());

  function toggleExpand(code) {
    setExpandedCodes((prev) => {
      const next = new Set(prev);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return next;
    });
  }

  function matches(node, term) {
    const t = term.toLowerCase();
    if (
      String(node.gl_code).includes(t) ||
      (node.description || "").toLowerCase().includes(t) ||
      (node.gl_class || "").toLowerCase().includes(t)
    ) {
      return true;
    }
    return (node.children || []).some((c) => matches(c, term));
  }

  function renderNodes(nodes, depth = 0) {
    return (nodes || [])
      .filter((n) => !search || matches(n, search))
      .map((node) => {
        const hasChildren = node.children?.length > 0;
        const isExpanded = expandedCodes.has(node.gl_code) || !!search;
        const indent = depth * 24;

        return (
          <div key={node.gl_code}>
            <div
              onClick={() => hasChildren && toggleExpand(node.gl_code)}
              className={`flex items-center border-b border-gray-100 py-2 transition hover:bg-gray-50 ${
                hasChildren ? "cursor-pointer" : ""
              }`}
              style={{ paddingLeft: `${indent + 16}px` }}
            >
              {hasChildren && (
                <span className="mr-2 w-4 text-center text-xs text-gray-400">
                  {isExpanded ? "\u25BC" : "\u25B6"}
                </span>
              )}
              {!hasChildren && <span className="mr-2 w-4" />}
              <span className="mr-3 rounded bg-gray-100 px-2 py-0.5 font-mono text-xs text-gray-700">
                {node.gl_code}
              </span>
              <span
                className={`text-sm ${depth === 0 ? "font-semibold text-gray-800" : depth === 1 ? "font-medium text-gray-700" : "text-gray-600"}`}
              >
                {node.gl_class}
              </span>
              {node.description && (
                <span className="ml-2 text-xs text-gray-400">
                  {node.description}
                </span>
              )}
              <span className="ml-auto text-xs text-gray-300">
                Level {node.gl_level}
              </span>
            </div>
            {hasChildren && isExpanded && renderNodes(node.children, depth + 1)}
          </div>
        );
      });
  }

  return (
    <div>
      <h2 className="mb-4 text-xl font-semibold text-gray-800">
        GL Code Reference
      </h2>

      <div className="mb-4">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Search GL codes..."
          className="w-64 rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
      </div>

      <div className="rounded-lg border border-gray-200 bg-white">
        {isLoading && (
          <p className="px-4 py-8 text-center text-gray-400">Loading...</p>
        )}
        {!isLoading && (!hierarchy || hierarchy.length === 0) && (
          <p className="px-4 py-8 text-center text-gray-400">
            No GL codes found.
          </p>
        )}
        {!isLoading && hierarchy && renderNodes(hierarchy)}
      </div>
    </div>
  );
}
