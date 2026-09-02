export function Button({
  as: Comp = 'button',
  variant = 'primary',
  size = 'md',
  className = '',
  ...props
}) {
  const base =
    'inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none'
  const sizes = {
    sm: 'px-3 py-1.5 text-sm',
    md: 'px-4 py-2.5 text-sm',
    lg: 'px-5 py-3 text-base',
  }
  const variants = {
    primary: 'bg-accent text-white hover:bg-accent-hover',
    secondary: 'bg-white text-text border border-line hover:bg-paper',
    ghost: 'text-muted hover:text-text hover:bg-paper',
    danger: 'bg-danger-soft text-danger hover:bg-danger hover:text-white',
    dark: 'bg-ink text-white hover:bg-ink-soft',
  }
  return (
    <Comp className={`${base} ${sizes[size]} ${variants[variant]} ${className}`} {...props} />
  )
}

export function Input({ label, hint, error, className = '', id, ...props }) {
  return (
    <label className="block" htmlFor={id}>
      {label && <span className="mb-1.5 block text-sm font-medium text-text">{label}</span>}
      <input
        id={id}
        className={`w-full rounded-lg border bg-white px-3.5 py-2.5 text-sm text-text placeholder:text-ink-muted focus:outline-none focus:ring-2 focus:ring-accent/30 ${
          error ? 'border-danger' : 'border-line focus:border-accent'
        } ${className}`}
        {...props}
      />
      {hint && !error && <span className="mt-1.5 block text-xs text-muted">{hint}</span>}
      {error && <span className="mt-1.5 block text-xs text-danger">{error}</span>}
    </label>
  )
}

export function Card({ className = '', children, ...props }) {
  return (
    <div
      className={`rounded-xl border border-line bg-card p-6 shadow-[0_1px_2px_rgba(20,21,31,0.04)] ${className}`}
      {...props}
    >
      {children}
    </div>
  )
}

export function Badge({ tone = 'muted', children }) {
  const tones = {
    muted: 'bg-paper text-muted border-line',
    success: 'bg-success-soft text-success border-transparent',
    warn: 'bg-warn-soft text-warn border-transparent',
    danger: 'bg-danger-soft text-danger border-transparent',
    accent: 'bg-accent-soft text-accent border-transparent',
  }
  return (
    <span
      className={`inline-flex items-center rounded-full border px-2.5 py-0.5 text-xs font-medium ${tones[tone]}`}
    >
      {children}
    </span>
  )
}

export function Alert({ tone = 'danger', children }) {
  const tones = {
    danger: 'bg-danger-soft text-danger',
    success: 'bg-success-soft text-success',
    warn: 'bg-warn-soft text-warn',
  }
  return <div className={`rounded-lg px-4 py-3 text-sm ${tones[tone]}`}>{children}</div>
}

export function PageHeader({ title, description, action }) {
  return (
    <div className="mb-8 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="font-display text-2xl font-semibold text-text">{title}</h1>
        {description && <p className="mt-1.5 text-sm text-muted">{description}</p>}
      </div>
      {action}
    </div>
  )
}

export function EmptyState({ icon: Icon, title, description, action }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-xl border border-dashed border-line px-6 py-16 text-center">
      {Icon && (
        <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-accent-soft text-accent">
          <Icon size={22} strokeWidth={1.75} />
        </div>
      )}
      <h3 className="font-display text-base font-semibold text-text">{title}</h3>
      {description && <p className="mt-1.5 max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  )
}

export function Spinner({ className = '' }) {
  return (
    <span
      className={`inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
    />
  )
}
