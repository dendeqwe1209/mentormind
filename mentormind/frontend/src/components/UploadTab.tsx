import React from "react";
import { Info } from "lucide-react";
import { UploadDocumentsTab } from "./UploadDocumentsTab";
import { UploadVideoCard } from "./UploadVideoCard";

// Spec 08 §3, page 4 "Tải dữ liệu": operation videos become draft steps for experts to review;
// documents go straight into the search index (spec 02), they have no review step.
export function UploadTab({ onReviewVideo }: { onReviewVideo: (videoId: string, processId: string) => void }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "1.75rem" }}>
      <UploadVideoCard onReview={onReviewVideo} />
      <div className="alert alert-info">
        <Info size={15} style={{ flexShrink: 0, marginTop: 2 }} />
        <span>
          Tài liệu (SOP, bản vẽ, bảng biểu) là nguồn chính thức: sau khi tải lên được đưa ngay vào kho tìm kiếm với nhãn
          đã chọn, không qua bước duyệt. Chỉ các bước trích từ video mới cần chuyên gia duyệt.
        </span>
      </div>
      <UploadDocumentsTab />
    </div>
  );
}
