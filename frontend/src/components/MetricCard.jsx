export default function MetricCard({ label, value, icon: Icon, tone = "default" }) {
  const toneClasses = {
    default: "text-indigo-400 border-white/10",
    danger: "text-red-400 border-red-500/30",
    success: "text-green-400 border-green-500/30",
    warning: "text-orange-400 border-orange-500/30",
  };

  return (
    <div className={`rounded-xl border bg-white/5 p-4 ${toneClasses[tone]}`}>
      <div className="flex items-center justify-between">
        <span className="text-sm text-gray-400">{label}</span>
        {Icon && <Icon size={18} className={toneClasses[tone].split(" ")[0]} />}
      </div>
      <div className="mt-2 text-3xl font-semibold text-white">{value}</div>
    </div>
  );
}
