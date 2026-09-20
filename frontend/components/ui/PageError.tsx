"use client";

/** Inline error with a retry action, shared by the data-loading pages. */
export function PageError({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div
      role="alert"
      className="rounded-md border border-outline bg-error-container p-4 flex flex-col sm:flex-row sm:items-center justify-between gap-3"
    >
      <p className="font-body-md text-body-md text-on-error-container font-medium">{message}</p>
      {onRetry && (
        <button
          onClick={onRetry}
          className="h-11 px-5 rounded-md bg-primary text-on-primary font-label-md text-label-md shrink-0"
        >
          Try again
        </button>
      )}
    </div>
  );
}
