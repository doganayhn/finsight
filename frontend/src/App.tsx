import { useBackendStatus } from './hooks/useBackendStatus'

export function App() {
  const { status, retry } = useBackendStatus()
  const indicator = status === 'Online' ? 'bg-emerald-600'
    : status === 'Offline' ? 'bg-red-600' : 'bg-amber-500'

  return (
    <main className="flex min-h-dvh items-center justify-center px-6 py-12">
      <section className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
        <div className="mb-8 flex h-11 w-11 items-center justify-center rounded-xl bg-emerald-900 text-xl font-semibold text-white" aria-hidden="true">F</div>
        <h1 className="text-4xl font-semibold tracking-tight">FinSight</h1>
        <p className="mt-3 text-base text-slate-600">Personal spending intelligence.</p>
        <div className="mt-9 border-t border-slate-100 pt-6">
          <p role="status" className="flex items-center gap-3 text-sm font-medium">
            <span aria-hidden="true" className={`h-2.5 w-2.5 rounded-full ${indicator}`} />
            Backend: {status}
          </p>
          {status === 'Offline' && (
            <p className="mt-3 text-sm leading-6 text-slate-600">We couldn’t connect. Please try again.</p>
          )}
          <button
            type="button"
            onClick={retry}
            disabled={status === 'Checking...'}
            className="mt-5 rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium transition hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-offset-4 focus-visible:outline-emerald-700 disabled:cursor-wait disabled:opacity-50"
          >
            Check connection
          </button>
        </div>
      </section>
    </main>
  )
}
