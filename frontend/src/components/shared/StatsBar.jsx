import { useStats } from "../../hooks/useTransactions";

function Stat({ label, value, color = "text-gray-800" }) {
  return (
    <div className="flex flex-col items-center px-4">
      <span className={`text-xl font-semibold ${color}`}>{value ?? "-"}</span>
      <span className="text-xs text-gray-500">{label}</span>
    </div>
  );
}

export default function StatsBar() {
  const { data, isLoading } = useStats();

  if (isLoading || !data) {
    return (
      <div className="mb-4 flex items-center justify-center rounded-lg border border-gray-200 bg-white py-3 text-sm text-gray-400">
        Loading stats...
      </div>
    );
  }

  const byStatus = data.by_review_status || {};
  const byConf = data.by_confidence || {};
  const byMethod = data.by_method || {};

  return (
    <div className="mb-4 flex flex-wrap items-center justify-start gap-2 divide-x divide-gray-200 rounded-lg border border-gray-200 bg-white py-3">
      <Stat label="Total" value={data.total_transactions} />
      <Stat
        label="Unreviewed"
        value={byStatus.Unreviewed || 0}
        color="text-gray-600"
      />
      <Stat
        label="High Conf."
        value={byConf.High || 0}
        color="text-green-600"
      />
      <Stat
        label="Medium Conf."
        value={byConf.Medium || 0}
        color="text-yellow-600"
      />
      <Stat label="Low Conf." value={byConf.Low || 0} color="text-red-600" />
      <Stat
        label="Unclassified"
        value={byMethod.Unclassified || 0}
        color="text-orange-600"
      />
      <Stat
        label="Flagged"
        value={byStatus.Flagged || 0}
        color="text-red-600"
      />
    </div>
  );
}
