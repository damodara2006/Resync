export function PageHeader({ eyebrow, title, description, status, actions }) {
  return (
    <div className="border-b border-slate-200 bg-white">
      <div className="mx-auto max-w-6xl px-6 py-8">
        <div className="flex flex-wrap items-start justify-between gap-6">
          <div>
            {eyebrow && (
              <span className="text-xs font-semibold uppercase tracking-wider text-indigo-600">
                {eyebrow}
              </span>
            )}
            <div className="mt-1 flex flex-wrap items-center gap-3">
              <h1 className="text-2xl font-semibold tracking-tight text-slate-900">{title}</h1>
              {status}
            </div>
            {description && (
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
                {description}
              </p>
            )}
          </div>
          {actions && <div className="flex shrink-0 items-center gap-3">{actions}</div>}
        </div>
      </div>
    </div>
  );
}

export function Section({ title, description, icon: Icon, actions, tone = "default", children }) {
  const toneClasses = {
    default: "border-slate-200 bg-white",
    accent: "border-emerald-200 bg-emerald-50/50",
  }[tone];

  return (
    <section className={`rounded-2xl border ${toneClasses} p-6 shadow-sm sm:p-7`}>
      {(title || actions) && (
        <div className="mb-5 flex flex-wrap items-center justify-between gap-4">
          <div>
            {title && (
              <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900">
                {Icon && <Icon size={18} className="text-slate-400" />}
                {title}
              </h2>
            )}
            {description && <p className="mt-1 text-sm text-slate-500">{description}</p>}
          </div>
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function PageContainer({ children, className = "" }) {
  return <div className={`mx-auto max-w-6xl px-6 py-10 ${className}`}>{children}</div>;
}
