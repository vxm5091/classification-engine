const confidenceColors = {
  High: "bg-green-100 text-green-800",
  Medium: "bg-yellow-100 text-yellow-800",
  Low: "bg-red-100 text-red-800",
};

const reviewColors = {
  Unreviewed: "bg-gray-100 text-gray-600",
  Approved: "bg-green-100 text-green-800",
  Reclassified: "bg-blue-100 text-blue-800",
  Flagged: "bg-red-100 text-red-800",
};

export function ConfidenceBadge({ value }) {
  if (!value) return null;
  const cls = confidenceColors[value] || "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {value}
    </span>
  );
}

export function ReviewBadge({ value }) {
  if (!value) return null;
  const cls = reviewColors[value] || "bg-gray-100 text-gray-600";
  return (
    <span
      className={`inline-block rounded-full px-2.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {value}
    </span>
  );
}
