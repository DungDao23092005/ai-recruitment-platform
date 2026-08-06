# 🏃 Sprint 1 Plan — Environment & Core Infrastructure Setup

- **Sprint Goal**: Khởi tạo toàn bộ cấu trúc mã nguồn Backend (FastAPI + Clean Architecture), Frontend (React + Vite + TS + Tailwind), thiết lập môi trường Docker Compose và kiểm tra kết nối với Database (MS SQL Server), Redis & Qdrant.
- **Thời lượng**: 1 tuần
- **Quy tắc tuân thủ**: [AGY.md](file:///D:/learn/Ai-Engineer-Lab/ai-recruitment-platform/docs/ai-agents/AGY.md) & [PROJECT_RULES.md](file:///D:/learn/Ai-Engineer-Lab/ai-recruitment-platform/docs/ai-agents/PROJECT_RULES.md)

---

## 📋 Danh Sách Tasks (Task Breakdown)

### 🔹 TASK 1.1: Thiết lập cấu trúc dự án Backend (FastAPI Clean Architecture)
- **Người thực hiện**: Implementation Engineer
- **Mô tả**: Tạo thư mục mã nguồn Backend tuân thủ Clean Architecture (`app/api`, `app/core`, `app/services`, `app/repositories`, `app/models`, `app/schemas`, `app/db`).
- **Tệp tin ảnh hưởng**:
  - `backend/app/main.py`
  - `backend/app/core/config.py`
  - `backend/app/db/session.py`
  - `backend/requirements.txt`
  - `docker/Dockerfile.backend`
- **Acceptance Criteria**:
  - [ ] Khởi chạy được ứng dụng FastAPI thành công với Python 3.12.
  - [ ] Khởi tạo endpoint kiểm tra sức khỏe hệ thống: `GET /api/v1/health`.
  - [ ] Truy cập được tài liệu Swagger UI tự động tại `http://localhost:8000/docs`.

---

### 🔹 TASK 1.2: Cấu hình kết nối CSDL Microsoft SQL Server & Alembic Migration
- **Người thực hiện**: Implementation Engineer
- **Mô tả**: Cấu hình Async SQLAlchemy 2.x kết nối MS SQL Server, tạo base model và khởi tạo Alembic.
- **Tệp tin ảnh hưởng**:
  - `backend/app/db/base_class.py`
  - `backend/app/db/session.py`
  - `backend/alembic.ini`
  - `backend/alembic/env.py`
- **Acceptance Criteria**:
  - [ ] Alembic khởi tạo và phát hiện được base models.
  - [ ] Kết nối thành công tới Microsoft SQL Server qua Docker.

---

### 🔹 TASK 1.3: Khởi tạo dự án Frontend (React 18 + TypeScript + Vite + TailwindCSS)
- **Người thực hiện**: Implementation Engineer
- **Mô tả**: Khởi tạo dự án Frontend trong thư mục `frontend/` sử dụng Vite, TypeScript, TailwindCSS và cài đặt shadcn/ui.
- **Tệp tin ảnh hưởng**:
  - `frontend/package.json`
  - `frontend/vite.config.ts`
  - `frontend/src/App.tsx`
  - `frontend/src/index.css`
  - `docker/Dockerfile.frontend`
- **Acceptance Criteria**:
  - [ ] Frontend khởi chạy mượt mà trên môi trường dev (`npm run dev`) tại cổng `3000`.
  - [ ] Cấu hình TailwindCSS hoạt động chính xác với phong cách thiết kế hiện đại, cao cấp.

---

### 🔹 TASK 1.4: Tối ưu Docker Compose cho toàn bộ hệ thống
- **Người thực hiện**: Implementation Engineer
- **Mô tả**: Cập nhật `docker-compose.yml` tích hợp đầy đủ 5 dịch vụ: `backend`, `frontend`, `postgres/mssql`, `redis`, `qdrant`.
- **Tệp tin ảnh hưởng**:
  - `docker-compose.yml`
  - `docker/Dockerfile.backend`
  - `docker/Dockerfile.frontend`
- **Acceptance Criteria**:
  - [ ] Lệnh `docker-compose up -d --build` khởi chạy thành công toàn bộ các dịch vụ mà không phát sinh lỗi.
  - [ ] Backend giao tiếp được với Database, Redis và Qdrant Vector DB.

---

## 🎯 Definition of Done (DoD) Cho Sprint 1
- Tất cả mã nguồn tuân thủ Clean Architecture, không hardcode credentials.
- Mã nguồn đầy đủ type hints và validation.
- Có lệnh kiểm thử tự động hoặc xác minh runtime thành công.
- Cập nhật tài liệu kỹ thuật tương ứng.
