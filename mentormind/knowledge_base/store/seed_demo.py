"""Seed initial sample WorkProfiles into SQLite ProfileStore for Demo & Testing."""

from datetime import datetime, timezone

from mentormind.core.schemas import (
    DataClassification,
    Evidence,
    ExceptionCase,
    Review,
    WorkProfile,
)
from mentormind.knowledge_base.store.profile_store import ProfileStore


def seed_demo_data(db_path: str = "data/work/profiles.sqlite") -> None:
    store = ProfileStore(db_path=db_path)

    sample_profiles = [
        WorkProfile(
            schema_version="1.0",
            profile_id="WP-PACK01-001",
            process_id="PACK01",
            step_order=1,
            step="Xác nhận lot và part number trên lệnh sản xuất",
            hand_action="Cầm phiếu chỉ thị bằng tay trái, đối soát mã vạch trên tem pallet",
            objects=["lệnh sản xuất", "tem pallet", "máy quét mã vạch"],
            key_point="So khớp từng ký tự mã lô và số lượng ghi trên lệnh",
            reason="Tránh lẫn lộn linh kiện khác đời xe gây lỗi lắp ráp tại công đoạn sau",
            reason_source="expert_verbal",
            exceptions=[],
            pass_criteria="Mã part trên tem trùng 100% với phiếu chỉ thị",
            evidence=Evidence(
                video_id="VID-PACK01-DEMO",
                t_start=0.0,
                t_end=4.8,
                keyframes=["kf_01.jpg"],
            ),
            confidence=0.98,
            generated_by="human",
            data_classification=DataClassification.SYNTHETIC,
            status="approved",
            review=Review(
                reviewer="Kỹ sư Trưởng DENSO QA",
                reviewed_at=datetime(2026, 9, 28, 8, 0, 0, tzinfo=timezone.utc),
                comment="Thao tác chuẩn xác theo SOP",
            ),
            created_at=datetime(2026, 9, 28, 7, 30, 0, tzinfo=timezone.utc),
            version=1,
        ),
        WorkProfile(
            schema_version="1.0",
            profile_id="WP-PACK01-002",
            process_id="PACK01",
            step_order=2,
            step="Kiểm tra ngoại quan linh kiện và chân connector",
            hand_action="Hai tay nâng linh kiện nghiêng 45 độ dưới đèn kiểm tra, soi chân cắm",
            objects=["linh kiện điều khiển", "đèn kiểm tra"],
            key_point="Quan sát kỹ độ thẳng của chân pin, không để chạm vào bề mặt kim loại",
            reason="Phát hiện sớm cong chân pin trước khi đóng vào khay định hình",
            reason_source="expert_interview",
            exceptions=[
                ExceptionCase(
                    case="Phát hiện chân pin cong hoặc xước",
                    handling="Dừng đóng gói, tách riêng vào khay NG và báo QC xác nhận",
                )
            ],
            pass_criteria="Không biến dạng, không rạn nứt vỏ nhựa, chân cắm thẳng đều",
            evidence=Evidence(
                video_id="VID-PACK01-DEMO",
                t_start=5.0,
                t_end=12.4,
                keyframes=["kf_02.jpg"],
            ),
            confidence=0.94,
            generated_by="human",
            data_classification=DataClassification.SYNTHETIC,
            status="in_review",
            created_at=datetime(2026, 9, 28, 8, 15, 0, tzinfo=timezone.utc),
            version=1,
        ),
        WorkProfile(
            schema_version="1.0",
            profile_id="WP-PACK01-003",
            process_id="PACK01",
            step_order=3,
            step="Đặt linh kiện vào khay định hình đúng chiều góc vát",
            hand_action="Dùng ngón cái và ngón trỏ giữ 2 gờ nhựa, hạ từ từ theo phương thẳng đứng",
            objects=["khay định hình", "linh kiện"],
            key_point="Đảm bảo góc vát linh kiện khớp hoàn toàn với rãnh khay",
            reason=None,
            reason_source=None,
            exceptions=[],
            pass_criteria="Linh kiện nằm êm, không kênh lệch",
            evidence=Evidence(
                video_id="VID-PACK01-DEMO",
                t_start=12.5,
                t_end=18.0,
                keyframes=["kf_03.jpg"],
            ),
            confidence=0.91,
            generated_by="vlm",
            data_classification=DataClassification.SYNTHETIC,
            status="draft",
            created_at=datetime(2026, 9, 28, 8, 30, 0, tzinfo=timezone.utc),
            version=1,
        ),
        WorkProfile(
            schema_version="1.0",
            profile_id="WP-PACK01-004",
            process_id="PACK01",
            step_order=4,
            step="Đóng nắp hộp carton và dán tem niêm phong",
            hand_action="Hai tay miết đều hai mép nắp hộp, gập nắp phụ trước nắp chính",
            objects=["hộp carton", "tem niêm phong"],
            key_point="Dùng lực miết đều 2 tay để mép nắp không bị lệch quá 2mm",
            reason=None,
            reason_source=None,
            exceptions=[],
            pass_criteria="Mép hộp khít đều, tem niêm phong dán phẳng ngay ngắn",
            evidence=Evidence(
                video_id="VID-PACK01-DEMO",
                t_start=18.5,
                t_end=24.0,
                keyframes=["kf_04.jpg"],
            ),
            confidence=0.89,
            generated_by="vlm",
            data_classification=DataClassification.SYNTHETIC,
            status="draft",
            created_at=datetime(2026, 9, 28, 8, 45, 0, tzinfo=timezone.utc),
            version=1,
        ),
    ]

    for p in sample_profiles:
        store.save_profile(p)
    print(f"Seeded {len(sample_profiles)} profiles into {db_path} successfully.")


if __name__ == "__main__":
    seed_demo_data()
