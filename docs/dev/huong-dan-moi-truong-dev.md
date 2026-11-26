# Build và chạy DW trên máy dev

Dành cho dev mới vào repo (đội DW2 trước tiên). Làm theo từ trên xuống: cuối
trang anh/chị có portal chạy trên máy, đăng nhập được bằng các vai DW1/DW2,
và chạy được test. Mọi lệnh `make` chạy trong **Git Bash**, ở thư mục gốc repo.

---

## 0. Đọc trước (15 phút)

| File                                       | Vì sao                                                                                                             |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| `CLAUDE.md`                                | Kiến trúc bắt buộc: lớp, ranh giới context, RLS, quy tắc migration, nhánh. Không làm trái mà không ghi quyết định. |
| `CONTEXT-MAP.md`                           | Các bounded context và cách chúng nói chuyện với nhau.                                                             |
| `packages/python/dw_purchasing/CONTEXT.md` | Từ vựng DW2 (dùng đúng từ này trong code và giao diện).                                                            |
| `.claude/plans/purchasing.md`              | DW2 đang ở đâu, việc tiếp theo, việc còn chờ khách.                                                                |
| `docs/dev/viec-chung-dw1-dw2.md`           | Phần nào là của chung, đừng viết lại trong DW2.                                                                    |

---

## 1. Cài đặt (một lần)

| Công cụ         | Phiên bản     | Ghi chú                                                         |
| --------------- | ------------- | --------------------------------------------------------------- |
| Docker Desktop  | bản mới, WSL2 | Đặt `.wslconfig` `memory=10GB` trên máy 16 GB.                  |
| Git for Windows | —             | Dùng **Git Bash** cho mọi lệnh `make`.                          |
| make            | —             | `winget install ezwinports.make`                                |
| uv              | ≥ 0.11        | Tự cài Python **3.12** theo `.python-version`.                  |
| Node.js         | ≥ 22          | Máy dev hiện dùng 24.                                           |
| pnpm            | **11.16.0**   | Đúng `packageManager` trong `package.json` (`corepack enable`). |
| Ollama          | tùy chọn      | Chỉ cần khi thử chat/model (mục 5).                             |

```sh
git clone <repo> dw-proterial && cd dw-proterial
make bootstrap        # uv sync --all-packages, pnpm install, tạo .env từ .env.example, cài pre-commit
```

**`.env`** do `make bootstrap` tạo từ `.env.example`. Ở local giữ giá trị mặc
định (`change-me-…`) là chạy được. Khóa thật (model ngoài, Strata, OpenAI…)
chỉ đặt trong `.env`, **không bao giờ commit**.

**RAM:** máy 16 GB chạy được nhưng sát. Đóng app nặng khi chạy full stack.

---

## 2. Hai cách chạy: chọn theo việc đang làm

|                    | `make dev`                                  | `make docker-up`                            |
| ------------------ | ------------------------------------------- | ------------------------------------------- |
| Dùng khi           | **Đang code**: sửa là thấy (hot reload)     | Demo, test đầu-cuối, thử chat với model     |
| API / worker / web | chạy trên máy                               | chạy trong Docker (image build sẵn)         |
| Trang mở lần đầu   | chậm (Next.js biên dịch từng trang lúc bấm) | nhanh                                       |
| Sửa code           | tự nạp lại                                  | phải `make docker-up` lại (build lại image) |
| Quét file đính kèm | `skip` (theo `.env`)                        | `clamd` (container `clamav`)                |

Hai cách **không chạy cùng lúc** (cùng cổng). `make dev` báo "port … already
in use" thì `make docker-down` trước.

### 2a. Chạy để code (`make dev`)

```sh
make infra-up          # Postgres, Qdrant, Valkey, S3, Keycloak, reader, docgen trong Docker
make migrate           # tạo/cập nhật schema
make demo-reset        # dữ liệu mẫu DW1 + persona + mật khẩu Keycloak cho mọi persona
set -a; . ./.env; set +a
uv run python -m dw_purchasing.testing.seed_personas   # vai DW2 cho các persona
make dev               # API + worker + web
```

`demo-reset` chạy seed nền tảng trước, nên chạy nó **trước** seed DW2. Hai
seed không đè lên nhau (mỗi bên chỉ đặt khóa của mình), chạy lại bao nhiêu
lần cũng được.

### 2b. Chạy full stack (`make docker-up`)

```sh
make docker-up         # build + chạy toàn bộ (lần đầu 15–30 phút)
make demo-reset
set -a; . ./.env; set +a
uv run python -m dw_purchasing.testing.seed_personas
```

Worker trong Docker **tự đọc hộp thư mẫu** sau khi reset (làn tự xử lý bật
mặc định).

### Cổng

Mặc định trong `.env.example` (máy nào đổi thì xem `.env` của máy đó):

| Dịch vụ          | Cổng mặc định                                        | Biến                               |
| ---------------- | ---------------------------------------------------- | ---------------------------------- |
| Web (`make dev`) | 3300                                                 | `DW_PUBLIC_WEB_URL`                |
| Web (Docker)     | 3000 (đặt `DW_WEB_HOST_PORT=3300` để đăng nhập được) | `DW_WEB_HOST_PORT`                 |
| API              | 8000                                                 | `DW_API_PORT` / `DW_API_HOST_PORT` |
| Keycloak         | 8686                                                 | `DW_KEYCLOAK_HOST_PORT`            |
| Postgres         | 5432                                                 | `DW_POSTGRES_HOST_PORT`            |

Keycloak chỉ cho phép đăng nhập quay về `localhost:3300`, nên web phải ở cổng 3300.

---

## 3. Đăng nhập

Mở web → tự chuyển sang Keycloak → đăng nhập **bằng email**, mật khẩu là
`DW_DEV_USER_PASSWORD` trong `.env`. (Một số tài khoản có sẵn trong realm có
username khác email, ví dụ `chi.le` có username `chi`; gõ email là chắc.)

Persona (danh sách đầy đủ: `configs/demo/demo_users.yaml`):

| Email                   | Vai DW1        | Vai DW2                                                |
| ----------------------- | -------------- | ------------------------------------------------------ |
| `an.nguyen@alpha.local` | sales_pic      | purchasing_requester (người yêu cầu)                   |
| `khoa.lam@alpha.local`  | sales_pic      | purchasing_buyer (nhân viên mua hàng)                  |
| `binh.tran@alpha.local` | —              | purchasing_head (trưởng mua hàng)                      |
| `tam.ngo@alpha.local`   | — (org_admin)  | purchasing_configurer (cấu hình)                       |
| `giang.do@alpha.local`  | sales_head     | —                                                      |
| `chi.le@alpha.local`    | platform_admin | —                                                      |
| `dung.vo@beta.local`    | —              | purchasing_buyer, **tenant khác** (thử cách ly tenant) |

Trang DW2 nằm dưới `/purchasing`.

---

## 4. Test và kiểm tra trước khi đẩy

```sh
uv run pytest packages/python/dw_purchasing -m unit    # unit của DW2 (nhanh, nên chạy thường xuyên)
make test-architecture   # ranh giới import + phụ thuộc khai báo
make test-integration    # cần `make infra-up`: RLS, repository, chéo tenant
make lint                # ruff check + ruff format --check + prettier + eslint
make typecheck           # mypy strict + tsc
pnpm --filter @dw/web test                              # unit test web (vitest)
make ci                  # cổng CI chạy ở máy (lâu)
```

- Unit cả repo (`make test-unit`) mất rất lâu; khi làm DW2 chạy theo thư mục như trên.
- `ruff format` / `--fix` **chỉ trên file mình sửa**, không chạy cho cả thư mục.
- Bài test mới phải chứng minh nó đỏ được: phá thứ nó bảo vệ, thấy đỏ, rồi trả lại.

---

## 5. Model (chỉ khi cần chat hoặc bước AI)

Mặc định các bước model **tắt** trong rules; chat "Hỏi DW1/DW2" thì cần model
để hiểu câu hỏi.

- Cài Ollama, kéo model chat (`qwen3.5-9b-dw`, xem `infra/onprem/README.md`).
- Profile `onprem` trong repo gọi model **`qwen3.8-flash-next-q2_0`** (model của
  nhà máy). Máy dev tạo bí danh, không tốn thêm ổ đĩa:
  `ollama cp qwen3.5-9b-dw qwen3.8-flash-next-q2_0`.
- `.env` đặt `DW_ONPREM_MODEL_BASE_URL=http://host.docker.internal:11434/v1`:
  đúng cho **Docker**. Với `make dev` (API chạy trên máy) địa chỉ này timeout;
  từ máy, Ollama trả lời ở `http://127.0.0.1:11434`. Muốn thử model khi
  `make dev` thì đổi biến đó trong `.env` của mình (đổi lại khi chạy Docker).
- Câu đầu tiên chờ ~1 phút (nạp model lên GPU), các câu sau vài giây.

---

## 6. Quy trình làm việc

- **Nhánh:** mỗi việc một nhánh tách từ `dev` → PR vào `dev` → khi ổn định, PR
  `dev` → `main` (release). Không push thẳng, không force-push `dev`/`main`.
- **Migration:** `uv run alembic -c db/alembic.ini revision -m "…"` (id ngẫu
  nhiên của alembic, không tự đặt số). Quyền (GRANT/REVOKE) đi cùng migration.
  Bảng tenant: `tenant_id`, `workspace_id`, RLS ENABLE + FORCE.
- **Ranh giới:** DW2 không import `dw_sales` (và ngược lại); cần gì của nhau
  thì khai Protocol ở phía dùng, composition root nối. Không import driver SQL
  Server ở đâu ngoài `apps/bravo-gateway` (CI chặn).
- **Giao diện:** chỉ antd (`antd`, `@ant-design/icons`, Ant Design X cho khung
  chat). Màu, chữ, bo góc lấy từ theme trong `@dw/ui`; Tailwind chỉ để bố cục.
- **Bước dùng model:** model đọc và viết; code kiểm và quyết. Đầu ra model luôn
  qua schema Pydantic rồi được code đối chiếu dữ liệu thật.

---

## 7. Hay vấp

| Triệu chứng                                             | Nguyên nhân / cách sửa                                                                                                                                                                                                                                            |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make dev` báo cổng đã dùng                             | Docker stack hoặc một `make dev` khác đang chạy: `make docker-down`.                                                                                                                                                                                              |
| Màn quản trị platform (Tenant/Operator/Support) lỗi 500 | Role `dw_provisioner` trong volume Postgres cũ sai mật khẩu. Chạy `DW_ADMIN_DATABASE_URL=postgresql+asyncpg://$POSTGRES_USER:$POSTGRES_PASSWORD@127.0.0.1:$DW_POSTGRES_HOST_PORT/postgres uv run python scripts/create_provisioner_role.py` (biến lấy từ `.env`). |
| Docker tự tắt giữa chừng                                | Hết RAM. Bật lại Docker Desktop, `make infra-up` (hoặc `make docker-up`); dữ liệu trong volume còn nguyên.                                                                                                                                                        |
| Không đăng nhập được một persona                        | Gõ **email**, không gõ username. Chưa có mật khẩu: chạy lại `make demo-reset`.                                                                                                                                                                                    |
| Chat trả "chưa hiểu câu hỏi"                            | Ollama tắt, thiếu bí danh model, hoặc `make dev` với `host.docker.internal` (mục 5).                                                                                                                                                                              |
| Thư có file "chưa đọc được tệp đính kèm" (Docker)       | Container `clamav` phải healthy; đừng tắt nó để lấy RAM.                                                                                                                                                                                                          |
| Trang đầu tiên rất chậm với `make dev`                  | Bình thường: Next.js biên dịch lúc bấm. Demo thì dùng `make docker-up`.                                                                                                                                                                                           |

---

## 8. Dọn khi xong

```sh
make docker-down        # hoặc make infra-down nếu chạy make dev (dữ liệu volume giữ nguyên)
docker desktop stop; wsl --shutdown   # trả RAM cho máy
```
