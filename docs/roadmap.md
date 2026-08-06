# 🗺️ Project Roadmap — AI Recruitment Platform

Lộ trình phát triển đồ án **AI Recruitment Platform** dành cho sinh viên Thực tập tốt nghiệp chuyên ngành AI Engineer.

---

## 📌 Tổng Quan Lộ Trình (Roadmap Overview)

Dự án được chia làm **6 Giai đoạn (Phases)** phát triển từ khởi tạo nền tảng đến khi hoàn thiện báo cáo và đóng gói sản phẩm.

```text
[Phase 1: Khởi tạo & Cấu trúc] ➔ [Phase 2: Core Features & Auth] ➔ [Phase 3: AI Engine Engine] 
                                                                         ↓
[Phase 6: Báo cáo & Nộp đồ án] ⬅ [Phase 5: Kiểm thử & Tối ưu] ⬅ [Phase 4: Advanced AI & RAG]
```

---

## 🚩 Chi Tiết Các Giai Đoạn (Detailed Phase Breakdown)

### 🔹 Phase 1: Setup Nền Tảng & Cấu Trúc Khung (Weeks 1 - 2)
- [x] Tạo cấu trúc thư mục chuẩn: `backend`, `frontend`, `docs`, `docker`, `scripts`, `.github`.
- [x] Tạo các tệp cấu hình cốt lõi (`.gitignore`, `README.md`, `docker-compose.yml`, `.env.example`, `LICENSE`).
- [ ] Cấu hình dự án FastAPI Backend với Clean Architecture (Routers, Services, Repositories).
- [ ] Cấu hình dự án React + TypeScript + Vite + TailwindCSS + shadcn/ui.
- [ ] Khởi tạo CSDL Microsoft SQL Server và thiết lập Alembic Migrations.
- [ ] Cấu hình kết nối Redis & Qdrant Vector Database qua Docker Compose.

---

### 🔹 Phase 2: Quản Lý Người Dùng & Chức Năng Cốt Lõi (Weeks 3 - 4)
- [ ] **Xác thực & Phân quyền**: Đăng ký, Đăng nhập JWT (Candidate, Recruiter, Admin).
- [ ] **Quản lý Hồ sơ Candidate**: Cập nhật thông tin cá nhân, mục tiêu nghề nghiệp, kỹ năng.
- [ ] **Quản lý Doanh nghiệp & Job Posting**: Tạo, sửa, xóa, tìm kiếm tin tuyển dụng.
- [ ] **Quản lý Ứng tuyển**: Candidate nộp đơn ứng tuyển, Recruiter duyệt trạng thái hồ sơ.
- [ ] **Admin Dashboard**: Quản lý người dùng, công ty, tin tuyển dụng.

---

### 🔹 Phase 3: Xây Dựng AI Matching & Parsing Engine (Weeks 5 - 7)
- [ ] **Resume Parsing Module**:
  - Trích xuất văn bản từ PDF (pdfplumber/PyPDF2).
  - Phân tích kỹ năng, học vấn, kinh nghiệm bằng LLM/NLP.
- [ ] **Job Description Parsing Module**:
  - Tự động trích xuất Required Skills, Preferred Skills, Experience Level.
- [ ] **Vector Embedding Engine**:
  - Tích hợp BGE Embedding Model (`BAAI/bge-m3` hoặc `bge-large-en-v1.5`).
  - Indexing Resume Vectors & Job Vectors vào Qdrant Vector DB.
- [ ] **Matching Engine**:
  - Tính toán Cosine Similarity giữa Vector Candidate & Vector Job.
  - Kết hợp Business Rules (Mức lương, địa điểm, số năm kinh nghiệm).

---

### 🔹 Phase 4: AI Đổi Mới - Explainable AI & RAG Chatbot (Weeks 8 - 10)
- [ ] **Explainable AI Engine**:
  - Sử dụng Gemini API sinh báo cáo chi tiết giải thích vì sao ứng viên phù hợp với công việc.
  - Đưa ra danh sách kỹ năng còn thiếu (Skill Gap Analysis) và lộ trình gợi ý.
- [ ] **Semantic Search**:
  - Cho phép tìm kiếm công việc/ứng viên theo ngữ cảnh thay vì từ khóa chính xác.
- [ ] **RAG AI Chatbot**:
  - Xây dựng Chatbot tư vấn bằng LangChain kết hợp Vector DB.
  - Hỗ trợ Candidate hỏi đáp về thông tin Job, công ty và quy trình tuyển dụng.
- [ ] **AI Interview Question Generator**:
  - Tự động gợi ý bộ câu hỏi phỏng vấn cho Nhà tuyển dụng dựa trên hồ sơ ứng viên.

---

### 🔹 Phase 5: Tối Ưu Hóa, Kiểm Thử & Giám Sát (Weeks 11 - 12)
- [ ] **AI Usage & Cost Monitoring**: Dashboard theo dõi lượt gọi AI API, thời gian phản hồi & token tiêu thụ.
- [ ] **Tối ưu Hiệu năng**: Cache kết quả Matching & Embeddings bằng Redis.
- [ ] **Kiểm thử (Testing)**:
  - Unit Test cho Backend Services & Repositories (pytest).
  - Integration Test cho luồng AI Matching & API endpoints.
- [ ] **Bảo mật & Rate Limiting**: Giới hạn số lượng request API & kiểm tra bảo mật OWASP.

---

### 🔹 Phase 6: Đóng Gói, Đóng Đồ Án & Báo Cáo (Weeks 13 - 14)
- [ ] Hoàn thiện CI/CD pipeline với GitHub Actions.
- [ ] Kiểm tra tính chuẩn xác của môi trường Docker Deployment.
- [ ] Viết Báo cáo Thực tập tốt nghiệp (Graduation Report).
- [ ] Chuẩn bị Slide & Demo Video cho buổi bảo vệ đồ án.

---

## 🎯 Tiêu Chí Đánh Giá Hoàn Thành (Definition of Done)
- [ ] Tất cả mã nguồn tuân thủ Clean Code, SOLID và Repository Pattern.
- [ ] Không có dữ liệu hardcode, không dùng code tạm.
- [ ] Hệ thống chạy mượt mà trên môi trường Docker Compose.
- [ ] AI Matching trả về kết quả chính xác có lời giải thích hợp lý.
