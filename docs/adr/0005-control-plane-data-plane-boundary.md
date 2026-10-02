---
status: Proposed
date: 2026-09-29
source:
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#hướng-đi-sau-phản-biện # hàng Kiến trúc lớp, Hybrid
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#23-profile-triển-khai
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#104-bảo-mật-và-niềm-tin # Mã hóa, Vị trí dữ liệu
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#11-quyết-định-thiết-kế-đã-chốt # Q14
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/process.md#131-dựng-hoàn-chỉnh-theo-phụ-thuộc # luồng A
    - https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/rule-spec.md#74-sec--an-ninh # SEC12
---

# Ranh giới control plane / data plane và năm hình thái triển khai P1–P5

> Viết trên nhánh `bidding` (sản phẩm E-HSDT, repo
> [platform-bidding](https://github.com/Datpt0205/platform-bidding)) ngày 29–30/9/2026
> và chép sang đây ngày 30/9/2026 vì là quyết định của nền tảng, dùng được cho mọi
> context. Ví dụ, mã `Dxx`, `TEN-xx`, `SECxx`, "ADR ctx" và các liên kết tới
> `docs/products/ehsdt/` là của E-HSDT, trỏ về repo đó. Trạng thái vẫn là Proposed.

Một mã nguồn phục vụ năm "profile triển khai" (ADR này gọi là hình thái, xem
điểm mở 8), từ nhà thầu vừa và nhỏ trên SaaS dùng chung tới tổng thầu, DNNN và
khách không cho dữ liệu hay kết nối ra ngoài. Quyết định: ngay từ thiết kế,
mọi thành phần được gắn nhãn **control plane** (điều phối, không chứa nội dung)
hoặc **data plane** (chứa nội dung). Control plane gồm tenant, license,
billing; registry phiên bản (rule pack, prompt, toolset, model profile,
template); định nghĩa graph; giám sát chỉ bằng id, trạng thái, số đếm, độ trễ.
Data plane gồm API và web của khách, PostgreSQL (RLS), object storage, Qdrant,
embedding, OCR và parser trong sandbox, agent runtime và worker, model gateway,
audit log, docgen.

| Hình thái               | Cách chạy                                                                                           |
| ----------------------- | --------------------------------------------------------------------------------------------------- |
| P1 SaaS dùng chung      | Một deployment production; mỗi khách một tenant, cách ly bằng RLS                                   |
| P2 SaaS nhiều workspace | Như P1; công ty tư vấn là một tenant, mỗi nhà thầu họ phục vụ là một workspace                      |
| P3 Tenant riêng         | Cụm riêng, database riêng, khóa mã hóa riêng (có thể BYOK), trên cloud của mình                     |
| P4 Hybrid               | Control plane ở mình; data plane ở VPC hoặc hạ tầng khách. Kết nối mTLS, data plane chủ động gọi ra |
| P5 On-prem đóng         | Cả hai plane ở khách, không kết nối ra. Rule pack, prompt, model cập nhật bằng gói có ký số         |

Ở mọi hình thái, cách ly tenant do PostgreSQL sở hữu. Data plane của khách có
PostgreSQL riêng, chạy cùng migration và cùng test RLS. Control plane không bao
giờ nhận nội dung tài liệu, giá hay dữ liệu cá nhân (`SEC12`: chỉ id, trạng
thái, số đếm, phiên bản). Mã hóa: TLS khi truyền, mã hóa khi lưu, khóa theo
tenant dạng envelope, BYOK cho P3–P5, xóa tenant bằng hủy khóa. Dữ liệu mặc
định lưu tại Việt Nam; ở P4, P5 thì nằm ở hạ tầng khách. Khách bảo mật cao
dùng P4 hoặc P5 (Q14).

Lý do nguồn nêu: tách control plane khỏi data plane về sau rất tốn, nên ranh
giới phải có từ đầu. Luồng A ở mục 13.1 dựng ranh giới này cùng P1–P5 trong
compose và helm, và ghi "bắt đầu ngay". Đây là khuyến nghị của process v0.4,
chưa được kiểm bằng phỏng vấn.

## Phương án đã cân nhắc

- Tách control plane khỏi data plane về sau, khi cần. Nguồn bác vì tách sau
  rất tốn.
- Bây giờ chỉ gắn nhãn plane và viết `SEC12` thành test hợp đồng, chưa dựng
  dịch vụ control plane. Lối này do digest nêu (`RULES-07`), dựa trên hiện
  trạng ở điểm mở 1; nguồn không bàn.

## Hệ quả

- Thành phần mới phải khai plane khi thiết kế; chứa nội dung thì thuộc data
  plane. `SEC12` thực thi ở contract control/data plane (rule-spec 7.4).
- Schema có một chủ là `db/migrations`; PostgreSQL của khách không có nhánh
  schema riêng. Định nghĩa hoàn chỉnh ở 13.1 đòi cả năm hình thái chạy cùng
  một bộ test.

## Xung đột và điểm mở

`process.md` và `rule-spec.md` bên dưới là file trong `docs/products/ehsdt/`.

1. **Kiến trúc của repo.** `CLAUDE.md:47` ghi "Modular monolith plus a separate
   async worker process"; `CLAUDE.md:291` đòi sửa file đó khi kiến trúc đổi.
   Control plane của P4 là một dịch vụ triển khai riêng. Repo chưa có gì cho
   nó: `infra/helm/`, `infra/terraform/` chỉ có `.gitkeep`, không có mã mTLS
   hay license (`RULES-07`, `SCAF-24`). Cần quyết: dựng dịch vụ ngay hay trước
   mắt chỉ gắn nhãn và test `SEC12`; sửa `CLAUDE.md` trên `main` theo đó.
2. **Chủ của tenant, license và quyền ở P4.** Để dựng `AccessContext`,
   `SqlMembershipLookup` join `platform.memberships` với `platform.tenants` rồi
   đọc `platform.entitlements` trong cùng database; thiếu hàng hoặc tenant
   không `active` thì từ chối
   (`packages/python/dw_platform/src/dw_platform/adapters/persistence/membership_lookup.py:90-142`).
   `entitlements`, `memberships`, `workspaces` có FK tới `platform.tenants`
   (`db/migrations/sql/0001_platform_baseline.sql:717,733,749`). Vậy PostgreSQL
   của data plane phải có các hàng này; control plane chỉ có thể là nguồn đồng
   bộ (`TEN-22`). Nguồn cũng không xếp Keycloak vào plane nào. Cần quyết: ai là
   chủ tenant, license, membership ở P4; chiều đồng bộ; data plane làm gì khi
   mất kết nối; Keycloak ở plane nào.
3. **Registry, `TenantOverlay` và ca eval ở P4.** Hôm nay registry nạp từ
   `configs/` đóng sẵn trong image (`infra/docker/api.Dockerfile:66-67`), và
   chưa có gì nạp lớp tenant (`MODEL-09`). `CLAUDE.md:175` đòi override của
   tenant nạp từ storage lúc chạy. Mẫu nội bộ của tenant (`process.md:415`) và
   ca eval OUT03 tạo từ dữ kiện gói (`rule-spec.md:408`) đều là nội dung, nên
   không được về control plane (`DOCS-54`, `ART-20`). Cần quyết: lớp platform
   tới data plane bằng cách nào; lớp tenant lưu ở đâu; cổng phát hành pack
   ("ca thật", `rule-spec.md:438-439`) dùng ca nào khi ca của khách P4, P5
   không ra khỏi data plane.
4. **Gói ký số và khóa theo tenant.** `scripts/release_manifest.py` băm nội
   dung bằng sha256 nhưng không ký, `.github/workflows/release.yml` cũng không
   (`SEC-34`). Repo không có mã envelope, KMS hay BYOK (`SEC-26`). Cần quyết:
   định dạng ký và nơi kiểm chữ ký khi nạp; KMS và phạm vi khóa cho từng hình
   thái.
5. **Lời gọi ra ngoài ở P4, P5.** P5 không kết nối ra. Parser gửi nguyên file
   cho mô hình qua `OPENAI_BASE_URL`, còn âm thanh đi Deepgram theo URL viết
   cứng (`dw_knowledge/adapters/api_parsers.py:28`; `MODEL-14`). Mỗi tiến trình
   chỉ có một endpoint mô hình (`MODEL-16`).
   `process.md:668` cho tra luật "đi web như DW01". Cần quyết: ở P4, P5 lời
   gọi nào được phép và thay bằng gì (xem
   [ADR 0006](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/adr/0006-model-routing-by-data-classification.md)).
6. **Quan sát.** Langfuse nhận trace OTLP
   (`packages/python/dw_observability/src/dw_observability/langfuse.py:1-6`),
   và span ghi nguyên văn thông điệp lỗi (`otel.py:149-150` cùng thư mục;
   `SEC-03`). Nguồn không nói Langfuse ở plane nào. Cần quyết: trace ở P4 dừng
   ở data plane hay sang control plane, và lọc gì trước khi sang.
7. **Danh sách trường được phép.** `process.md:185` ghi "id, trạng thái, số
   đếm, độ trễ"; `rule-spec.md:400` ghi "id, trạng thái, số đếm, phiên bản" và
   chỉ nói "Ở profile hybrid", còn `process.md:190` nói "không bao giờ". Cần
   quyết: contract giữ danh sách trường nào, và `SEC12` áp cho hình thái nào.
8. **Chữ "profile" và "data plane".** Nguồn gọi P1–P5 là "profile triển
   khai". Trong repo, `Profile` (`apps/api/src/dw_api/settings.py:27-28`) là
   môi trường `local | test | uat | production`, và `CLAUDE.md:253-257` chỉ cho
   chặn theo `settings.is_deployed`, không theo `profile == "production"`;
   model profile là file trong `configs/models/`.
   `infra/compose/docker-compose.yml:5` đã gọi compose profile `infra` là "data
   plane only" (`RULES-06`). Cần quyết: tên cho P1–P5, và "cùng một bộ test"
   chạy trên tổ hợp nào.
9. **Thời điểm.** 13.1 cho luồng A "bắt đầu ngay", còn
   `.claude/plans/bidding.md:63,97` đặt phỏng vấn trước code sâu và
   `bidding.md:15-18` đòi thay đổi nền tảng lên `main` trước (`SCAF-23`,
   `RULES-09`). Cần quyết: luồng A có chờ phỏng vấn không, phần nào làm trên
   `main`.

Các mã như `TEN-02`, `DOCS-15` là mục trong [bản đối chiếu tài liệu với repo ngày 29/9/2026](https://github.com/Datpt0205/platform-bidding/blob/bidding/docs/products/ehsdt/audit-2026-09-29.md).
