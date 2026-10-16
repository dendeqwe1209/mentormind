import React, { useEffect } from "react";
import { AlertTriangle, Trash2 } from "lucide-react";

// Spec 08 §3: every delete asks first. "Huỷ", Escape or a click outside closes without a request.
export function ConfirmDialog({
  title,
  children,
  confirmLabel = "Xoá",
  onConfirm,
  onCancel,
}: {
  title: string;
  children: React.ReactNode;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onCancel(); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onCancel]);

  return (
    <div className="modal-backdrop" onClick={onCancel}>
      <div className="modal" role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" onClick={(e) => e.stopPropagation()}>
        <div className="card-header">
          <div className="card-title" id="confirm-title">
            <div className="card-icon ci-danger">
              <AlertTriangle size={14} />
            </div>
            {title}
          </div>
        </div>
        <div className="modal-body">
          {children}
          <p><strong>Không thể hoàn tác.</strong></p>
        </div>
        <div className="modal-actions">
          <button id="btn-confirm-cancel" className="btn btn-ghost" onClick={onCancel} autoFocus>
            Huỷ
          </button>
          <button id="btn-confirm-delete" className="btn btn-danger" onClick={onConfirm}>
            <Trash2 size={14} />
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
