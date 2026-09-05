export default function Footer() {
  return (
    <footer className="border-t border-slate-200 bg-white">
      <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-2 px-6 py-6 text-xs text-slate-400">
        <span>
          Re<span className="text-indigo-500">sync</span> — payment reconciliation demo
        </span>
        <span>Test-mode payments only. No real charges are made.</span>
      </div>
    </footer>
  );
}
