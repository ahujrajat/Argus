interface Props {
  isFactory: boolean;
  isDirty: boolean;
  onSave: () => void;
  onClone: () => void;
  onReset: () => void;
  onDelete: () => void;
}

export function PipelineToolbar({ isFactory, isDirty, onSave, onClone, onReset, onDelete }: Props) {
  return (
    <div className="flex items-center gap-2">
      {isFactory && (
        <span className="inline-flex items-center gap-1 px-2 py-1 bg-gray-100 border border-gray-200 rounded-md text-[11px] font-medium text-gray-500">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z" />
          </svg>
          Factory
        </span>
      )}

      {!isFactory && (
        <>
          <button
            onClick={onReset}
            disabled={!isDirty}
            className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Reset
          </button>
          <button
            onClick={onSave}
            disabled={!isDirty}
            className="px-3 py-1.5 text-xs font-semibold bg-accent-600 text-white rounded-lg hover:bg-accent-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            Save
          </button>
        </>
      )}

      <button
        onClick={onClone}
        className="px-3 py-1.5 text-xs font-medium text-gray-600 border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors"
      >
        Clone
      </button>

      {!isFactory && (
        <button
          onClick={onDelete}
          className="px-3 py-1.5 text-xs font-medium text-red-600 border border-red-200 rounded-lg hover:bg-red-50 transition-colors"
        >
          Delete
        </button>
      )}
    </div>
  );
}
