# Build và chạy DW trên máy dev (Windows)

Dành cho dev mới vào repo (đội DW2 trước tiên). Làm đúng thứ tự từ mục 1 đến
mục 7: cuối mục 6 anh/chị có portal chạy trên máy, đăng nhập được bằng các vai
DW1/DW2; mục 7 thêm model AI chạy trên máy để thử chat. Mọi lệnh chạy trong
**Git Bash**, ở thư mục gốc repo, trừ chỗ ghi rõ PowerShell.

Đã thử trên: Windows 10/11, Docker Desktop (WSL2), uv 0.11, Node 24, pnpm
11.16.0, Ollama 0.40, GPU GTX 1080 8 GB.

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

## 1. Máy cần gì

| Hạng mục | Tối thiểu                            | Ghi chú                                                                                                 |
| -------- | ------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| RAM      | 16 GB                                | Chạy được nhưng sát; 32 GB thoải mái. Docker dùng tối đa 10 GB (mục 2).                                 |
| Ổ đĩa    | 60 GB trống                          | Image Docker ~15 GB, `node_modules` + `.venv` ~5 GB, model AI ~7 GB.                                    |
| GPU      | không bắt buộc                       | Chỉ để chạy model AI trên máy (mục 7): NVIDIA ≥ 8 GB VRAM. Không có GPU: chạy được mọi thứ trừ chat AI. |
| Mạng     | Internet lần đầu                     | Tải gói Python/Node, image Docker (Docker Hub, quay.io, ghcr.io, đều công khai), model.                 |
| GitHub   | được mời vào repo (repo **private**) | Xin anh Đạt quyền; clone bằng HTTPS với token hoặc SSH key.                                             |

---

## 2. Cài công cụ (một lần)

PowerShell (quyền admin cho Docker):

```powershell
winget install Git.Git
winget install Docker.DockerDesktop
winget install ezwinports.make
winget install astral-sh.uv
winget install OpenJS.NodeJS.LTS
winget install Ollama.Ollama        # chỉ khi thử model AI (mục 7)
```

Mở lại terminal, rồi trong **Git Bash**:

```sh
corepack enable                      # pnpm đúng bản 11.16.0 theo package.json
pnpm --version                       # phải in 11.16.0
uv --version; node --version; make --version; docker --version
```

**Giới hạn RAM cho Docker.** Tạo file `C:\Users\<tên>\.wslconfig`:

```ini
[wsl2]
memory=10GB
processors=4
swap=4GB
```

Rồi PowerShell: `wsl --shutdown`, mở lại Docker Desktop. Không đặt giới hạn
thì Docker ăn hết RAM và Windows treo; đặt thấp hơn 8 GB thì Keycloak, ClamAV
và reader không đủ chỗ.

---

## 3. Lấy code và cài phụ thuộc

```sh
git clone https://github.com/<org>/dw-proterial.git    # link repo xin anh Đạt
cd dw-proterial
git checkout dev                                       # luôn làm từ dev, không ở main
make bootstrap
```

`make bootstrap` làm 4 việc: `uv sync --all-packages` (tự cài Python 3.12 và
mọi package Python), `pnpm install`, **chép `.env.example` thành `.env`** nếu
chưa có, và cài hook pre-commit. Lần đầu ~5–10 phút.

---

## 4. File `.env`

`.env` nằm ở gốc repo, **không bao giờ commit** (đã có trong `.gitignore`).
Giá trị mặc định chạy được ngay trên máy; chỉ đổi khi một trong các trường hợp
dưới đây xảy ra.

### 4a. Không cần đổi gì nếu…

máy chưa có Postgres/Keycloak nào chạy sẵn ở cổng 5432/8686/8000/3300. Các
nhóm biến chính, để biết mình đang chạm vào gì:

| Nhóm                  | Biến                                                                              | Mặc định / ý nghĩa                                                                                                                                                                |
| --------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Tên dự án Docker      | `COMPOSE_PROJECT_NAME`                                                            | `dw`: tên các volume. Hai bản checkout cùng tên dùng **chung** dữ liệu Postgres.                                                                                                  |
| Postgres              | `POSTGRES_USER`, `POSTGRES_PASSWORD`, `DW_DB_*_PASSWORD`, `DW_*_DATABASE_URL`     | Các role `dw_admin`, `dw_migrator`, `dw_app`, `dw_agent_ro`, `dw_provisioner`. Mật khẩu lặp lại trong URL: đổi thì đổi cả hai chỗ. Role chỉ được tạo **lần đầu** volume khởi tạo. |
| Keycloak              | `KEYCLOAK_ADMIN_PASSWORD`, `OIDC_ISSUER_URL`, `DW_API_ACCOUNTS_CLIENT_SECRET`     | Realm `dw`, client `dw-web`. Đăng nhập admin Keycloak: `http://localhost:8686` với `admin` / `KEYCLOAK_ADMIN_PASSWORD`.                                                           |
| Mật khẩu persona demo | `DW_DEV_USER_PASSWORD`                                                            | `change-me-dev-user`: mật khẩu `make demo-reset` đặt cho mọi persona. Tối thiểu 10 ký tự, khác username/email.                                                                    |
| Cổng web              | `DW_PUBLIC_WEB_URL=http://localhost:3300`, `DW_WEB_HOST_PORT=3300`                | Keycloak **chỉ** cho quay về `localhost:3300`; đừng đổi cổng web.                                                                                                                 |
| Quét file đính kèm    | `DW_SALES_MALWARE_SCAN=skip`                                                      | Chỉ cho `make dev`. Docker luôn quét bằng ClamAV.                                                                                                                                 |
| Model                 | `DW_MODEL_PROVIDER=mock`, `DW_ONPREM_MODEL_BASE_URL` (đang comment)               | Không có model thì portal vẫn chạy; xem mục 7.                                                                                                                                    |
| Push iPhone           | `DW_WEB_PUSH_*`                                                                   | `make dev` tự sinh khóa VAPID vào `.env` lần đầu.                                                                                                                                 |
| Khóa ngoài (bí mật)   | `OPENAI_API_KEY`, `ZALO_*`, `TELEGRAM_*`, `DW_BRAVO_*`, `DW_APPROVAL_CODE_SECRET` | Để trống. Ai được cấp khóa thì chỉ đặt trong `.env` của mình.                                                                                                                     |

### 4b. Đổi khi cổng bị chiếm

Bỏ comment và đổi cổng tương ứng ở đầu `.env` (`DW_POSTGRES_HOST_PORT`,
`DW_KEYCLOAK_HOST_PORT`, `DW_API_HOST_PORT`…), rồi sửa cùng cổng trong các URL
phía dưới (`DW_*_DATABASE_URL`, `OIDC_ISSUER_URL`). Đổi cổng Keycloak thì đặt
thêm `KC_HOSTNAME` cho khớp. Không đổi `DW_WEB_HOST_PORT` (lý do ở bảng trên).

### 4c. Lưu ý khi sửa `.env`

- `make bootstrap` **không** cập nhật `.env` đã có. Sau khi `git pull`, so
  `.env.example` với `.env` (`git diff --no-index .env.example .env`) và chép
  thêm biến mới.
- Đừng dùng ký tự `$` trong giá trị: `make` đọc `.env` và hiểu `$` là biến.
- Một biến mật khẩu Postgres đổi sau khi volume đã tạo thì role cũ vẫn giữ mật
  khẩu cũ: xóa volume (`docker volume rm dw_postgres-data`, mất dữ liệu) hoặc
  xem mục 9.

---

## 5. Chạy lần đầu (khuyên dùng: toàn bộ trong Docker)

```sh
make docker-up       # build 5 image + chạy toàn bộ; lần đầu 15–30 phút
make demo-reset      # dữ liệu mẫu DW1, persona, mật khẩu Keycloak cho mọi persona
set -a; . ./.env; set +a
uv run python -m dw_purchasing.testing.seed_personas    # vai DW2 cho các persona
```

`make docker-up` tự chạy migration (container `migrate`) và chờ mọi dịch vụ
healthy. Lỗi giữa chừng thì xem mục 9 trước khi chạy lại.

**Kiểm tra:** `docker ps` thấy `api`, `worker`, `web`, `postgres`, `keycloak`,
`clamav`, `reader` đều `healthy`. Mở `http://localhost:3300`.

Worker trong Docker **tự đọc hộp thư mẫu** sau khi reset, nên vài phút sau
trang Hộp thư DW1 có thư.

## 6. Đăng nhập

Mở `http://localhost:3300` → tự chuyển sang Keycloak → gõ **email** (không gõ
username), mật khẩu là `DW_DEV_USER_PASSWORD` trong `.env`.

Persona (người giả lập; đủ trong `configs/demo/demo_users.yaml`):

| Email                    | Tenant | DW1 (Sales)                                         | DW2 (Mua hàng)                          |
| ------------------------ | ------ | --------------------------------------------------- | --------------------------------------- |
| `an.nguyen@alpha.local`  | Alpha  | PIC đơn hàng, kiểm soát xuất khẩu                   | người yêu cầu                           |
| `dieu.hoang@alpha.local` | Alpha  | PIC báo giá, xem giá khách khác                     | —                                       |
| `khoa.lam@alpha.local`   | Alpha  | PIC, duyệt báo giá thay                             | nhân viên mua hàng                      |
| `giang.do@alpha.local`   | Alpha  | Trưởng Sales: duyệt báo giá, giao việc              | duyệt bậc cuối                          |
| `binh.tran@alpha.local`  | Alpha  | — (bị từ chối ở mọi trang Sales)                    | trưởng phòng Mua hàng                   |
| `tam.ngo@alpha.local`    | Alpha  | IT quản trị tenant, đề xuất quy tắc (không xem giá) | người cấu hình                          |
| `ha.vu@alpha.local`      | Alpha  | lãnh đạo, chỉ xem tổng quan                         | —                                       |
| `chi.le@alpha.local`     | Alpha  | quản trị nền tảng (đừng dùng để thử quyền)          | —                                       |
| `bao.pham@beta.local`    | Beta   | PIC (thử cách ly tenant)                            | —                                       |
| `dung.vo@beta.local`     | Beta   | —                                                   | nhân viên mua hàng (thử cách ly tenant) |

Trang DW1 ở `/sales`, DW2 ở `/purchasing`.

### 6a. Chạy để code (`make dev`, sửa là thấy)

Khi đã quen, code hằng ngày dùng `make dev`: hạ tầng trong Docker, API/worker/
web chạy trên máy và tự nạp lại khi sửa.

```sh
make docker-down       # nếu đang chạy full Docker (hai cách dùng chung cổng)
make infra-up          # Postgres, Qdrant, Valkey, S3, Keycloak, reader, docgen
make migrate
make demo-reset        # chỉ cần khi muốn dữ liệu sạch
set -a; . ./.env; set +a; uv run python -m dw_purchasing.testing.seed_personas
make dev               # API :8000 + worker + web :3300
```

|                    | `make dev`                               | `make docker-up`                 |
| ------------------ | ---------------------------------------- | -------------------------------- |
| Dùng khi           | đang code                                | demo, test đầu-cuối, thử chat AI |
| Trang mở lần đầu   | chậm (Next.js biên dịch lúc bấm)         | nhanh                            |
| Sửa code           | tự nạp lại                               | `make docker-up` lại (build lại) |
| Quét file đính kèm | `skip`                                   | ClamAV                           |
| Model AI           | `DW_ONPREM_MODEL_BASE_URL` = `127.0.0.1` | `host.docker.internal` (mục 7)   |

---

## 7. Model AI trên máy (để thử chat "Hỏi DW1/DW2")

**Không có model, portal vẫn chạy đủ.** `make demo-reset` cài bộ quy tắc với
mọi bước model **tắt**; chỉ chat cần model để hiểu câu hỏi (không có model
thì chat trả "chưa hiểu câu hỏi lúc này").

DW1/DW2 luôn gọi profile `onprem` (`configs/models/onprem.yaml`), tên model
`qwen3.8-flash-next-q2_0` (model của nhà máy). Trên máy dev ta dùng Qwen3.5 9B
và đặt bí danh trùng tên đó.

### 7a. Cài model (một lần, cần GPU NVIDIA ≥ 8 GB)

```sh
ollama pull qwen3.5:9b                                                 # ~6.6 GB
ollama create qwen3.5-9b-dw -f infra/onprem/Modelfile.qwen3.5-9b-dw   # thêm num_ctx 8192
ollama cp qwen3.5-9b-dw qwen3.8-flash-next-q2_0                       # bí danh, không tốn thêm ổ
ollama list                                                            # thấy cả 3 tên
curl -s http://127.0.0.1:11434/v1/models                               # Ollama đang chạy
```

Không có GPU: chạy bằng CPU được nhưng chậm ~10 lần, quá thời gian chờ 120
giây của mỗi bước; không nên.

### 7b. Trỏ DW tới model

Bỏ comment và đặt trong `.env`, **theo cách đang chạy**:

```sh
# make docker-up (API/worker trong container):
DW_ONPREM_MODEL_BASE_URL=http://host.docker.internal:11434/v1
# make dev (API/worker trên máy):
DW_ONPREM_MODEL_BASE_URL=http://127.0.0.1:11434/v1
```

Đặt nhầm thì chat chờ hết hạn rồi trả "chưa hiểu". Sau khi đổi: `make
docker-up` lại (hoặc dừng và chạy lại `make dev`).

**Kiểm tra:** mở widget "Hỏi DW1" (góc phải dưới trang `/sales`), bấm một câu
gợi ý. Câu đầu chờ ~1 phút (Ollama nạp model lên GPU), các câu sau vài giây.
Ollama chỉ trả lời một câu mỗi lúc.

### 7c. Bật các bước model (không cần cho việc code thường ngày)

Một bước model chỉ bật được khi đã đo đạt ngưỡng trên model thật:
`uv run python scripts/run_evals.py --live onprem --attest --tenant <tenant> --workspace <workspace>`,
rồi đề xuất phiên bản quy tắc ở `/sales/rules` (người thứ hai duyệt). Bật mà
chưa đo thì bị từ chối (409). Embedding (bge-m3) không cần trên máy:
`DW_*_EMBEDDING_PROVIDER=hash`.

---

## 8. Test và kiểm tra trước khi đẩy

```sh
uv run pytest packages/python/dw_purchasing -m unit    # unit của DW2 (nhanh)
make test-architecture   # ranh giới import + phụ thuộc khai báo
make test-integration    # cần make infra-up: RLS, repository, chéo tenant
make lint                # ruff check + ruff format --check + prettier + eslint
make typecheck           # mypy strict + tsc
pnpm --filter @dw/web test                              # unit test web (vitest)
make ci                  # cổng CI chạy ở máy (lâu)
```

- Unit cả repo (`make test-unit`) mất rất lâu; khi làm DW2 chạy theo thư mục.
- `ruff format` / `--fix` **chỉ trên file mình sửa**, không chạy cho cả thư mục.
- Bài test mới phải chứng minh nó đỏ được: phá thứ nó bảo vệ, thấy đỏ, rồi trả lại.

**Quy trình:**

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

## 9. Hay vấp

| Triệu chứng                                             | Nguyên nhân / cách sửa                                                                                                                               |
| ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `make demo-reset` báo `DW_DEV_USER_PASSWORD is not set` | `.env` tạo từ bản cũ của `.env.example`. Thêm `DW_DEV_USER_PASSWORD=change-me-dev-user` (mục 4c).                                                    |
| `make dev` báo cổng đã dùng                             | Docker stack hoặc một `make dev` khác đang chạy: `make docker-down`.                                                                                 |
| Đăng nhập xong bị Keycloak báo "Invalid redirect uri"   | Web không ở cổng 3300: kiểm `DW_WEB_HOST_PORT=3300` và `DW_PUBLIC_WEB_URL` trong `.env`.                                                             |
| Không đăng nhập được một persona                        | Gõ **email**, không gõ username. Chưa có mật khẩu: chạy lại `make demo-reset`.                                                                       |
| Màn quản trị platform (Tenant/Operator/Support) lỗi 500 | Role `dw_provisioner` trong volume cũ sai mật khẩu: `set -a; . ./.env; set +a; uv run python scripts/create_provisioner_role.py`.                    |
| Docker tự tắt giữa chừng                                | Hết RAM. Kiểm `.wslconfig` (mục 2), đóng app nặng, bật lại Docker Desktop, `make infra-up` (hoặc `make docker-up`); dữ liệu trong volume còn nguyên. |
| Thư mãi "Đang chờ DW1"                                  | Worker hoặc reader chưa chạy: `docker ps`, xem `docker logs <tên>-worker-1`.                                                                         |
| Thư có file "chưa đọc được tệp đính kèm" (Docker)       | Container `clamav` phải healthy (khởi động ~3 phút); đừng tắt nó để lấy RAM.                                                                         |
| Chat trả "chưa hiểu câu hỏi"                            | Ollama tắt, thiếu bí danh model, hoặc `DW_ONPREM_MODEL_BASE_URL` không đúng cách đang chạy (mục 7b).                                                 |
| Trang đầu tiên rất chậm với `make dev`                  | Bình thường: Next.js biên dịch lúc bấm. Demo thì dùng `make docker-up`.                                                                              |
| Sửa realm Keycloak trong repo mà không thấy đổi         | Realm chỉ được nạp khi DB Keycloak trống. Xóa volume Keycloak/Postgres hoặc sửa tay ở trang admin.                                                   |

---

## 10. Dọn khi xong

```sh
make docker-down        # hoặc make infra-down nếu chạy make dev (dữ liệu volume giữ nguyên)
```

PowerShell, để trả RAM cho máy:

```powershell
docker desktop stop; wsl --shutdown
```
