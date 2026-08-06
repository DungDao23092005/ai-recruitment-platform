# 💻 Technology Stack & Architectural Decisions

Tài liệu chi tiết về các công nghệ được lựa chọn và lý do sử dụng cho dự án **AI Recruitment Platform**.

---

## 🏛️ 1. Danh Sách Công Nghệ (Tech Stack Matrix)

| Phân vùng | Công nghệ | Phiên bản / Thư viện chính | Lý do chọn lựa |
| :--- | :--- | :--- | :--- |
| **Frontend** | React | 18.x + TypeScript | Phổ biến, hiệu năng cao với Virtual DOM, dễ bảo trì với Type Safety. |
| | Vite | Latest | Tốc độ Build & HMR cực nhanh so với Webpack truyền thống. |
| | TailwindCSS | 3.x / 4.x | Thiết kế UI linh hoạt, nhất quán và hiện đại. |
| | shadcn/ui | Latest | Bộ component Accessible, thẩm mỹ cao và dễ tùy biến. |
| **Backend** | FastAPI | Python 3.12 | Tốc độ xử lý asynchronous (async/await) hàng đầu, hỗ trợ Pydantic type validation & tự động sinh OpenAPI docs. |
| | SQLAlchemy | 2.x (Async) | ORM tiêu chuẩn ngành cho Python, hỗ trợ Repository Pattern và kết nối linh hoạt. |
| | Alembic | Latest | Quản lý Database Schema Migrations an toàn và chính xác. |
| | Pydantic | v2.x | Data validation và serialization siêu nhanh viết bằng Rust. |
| **Database** | MS SQL Server | 2019 / 2022 | Cơ sở dữ liệu quan hệ mạnh mẽ, tuân thủ yêu cầu đồ án. |
| **Caching** | Redis | 7.x Alpine | Lưu trữ Session, Cache kết quả Embedding/Matching Score và làm Message Queue. |
| **Vector DB** | Qdrant | Latest | Vector Database siêu tốc cho Semantic Search & Similarity Calculation, hỗ trợ lọc Payload linh hoạt. |
| **AI / NLP** | BGE Embedding | BAAI/bge-m3 | Top 1 Embedding Model đa ngôn ngữ (Hỗ trợ tốt Tiếng Việt & Tiếng Anh). |
| | Gemini API | Google Gemini 1.5/2.0 | LLM tốc độ cao, ngữ cảnh lớn cho RAG Chatbot, Explainable AI & Interview Question Generator. |
| | LangChain | Latest | Framework điều phối RAG pipeline, Prompt Templates & Agent Chains. |
| **DevOps** | Docker | Latest | Đóng gói môi trường nhất quán từ Development đến Production. |
| | GitHub Actions| Latest | Tự động hóa CI/CD, Linting & Automated Testing. |

---

## 🔍 2. Chi Tiết Lựa Chọn Công Nghệ Nổi Bật

### 2.1. Backend Framework: FastAPI vs Django / Flask
- **FastAPI** được chọn vì hỗ trợ native **Asynchronous IO**, rất thích hợp khi gọi đồng thời nhiều dịch vụ AI ngoài (Gemini API, Qdrant Vector Store).
- Tích hợp sẵn **Swagger UI (`/docs`)** giúp kiểm thử API nhanh chóng mà không cần viết tài liệu thủ công.

### 2.2. Vector Database: Qdrant vs Milvus / Pinecone
- **Qdrant** viết bằng Rust, tiêu tốn ít RAM, hỗ trợ Docker container cực kỳ nhẹ nhàng cho môi trường Local Development.
- Hỗ trợ **Payload Filtering** mạnh mẽ, cho phép lọc công việc theo địa điểm/khoảng lương trước khi tính Cosine Similarity.

### 2.3. Embedding Model: BGE (BAAI) vs OpenAI Embeddings
- **BGE Embedding (`BAAI/bge-m3`)** là mô hình Open-Source xuất sắc nhất cho tìm kiếm ngữ nghĩa đa ngôn ngữ, cho phép chạy hoàn toàn Offline/Local hoặc deploy riêng để tiết kiệm chi phí.

### 2.4. Generative AI & RAG: Gemini API + LangChain
- **Gemini API**: Tốc độ phản hồi cực nhanh, chi phí tối ưu và khả năng xử lý Prompt dài vượt trội.
- **LangChain**: Giúp cấu trúc luồng RAG (Retrieval-Augmented Generation) mạch lạc, hỗ trợ Chat Memory và Document Loaders cho file PDF CV.

---

## 🔒 3. Bảo Mật & Chuẩn Mã Nguồn (Security & Code Standards)

1. **Chuẩn mã nguồn**:
   - Tuân thủ PEP 8 cho Python Backend.
   - Tuân thủ ESLint & Prettier cho React Frontend.
   - Áp dụng Type Annotation đầy đủ trên cả Frontend (TypeScript) và Backend (Python Type Hints).

2. **Bảo mật**:
   - **Xác thực**: JWT (JSON Web Tokens) với Access Token & Refresh Token.
   - **Mật khẩu**: Hash với thuật toán Argon2 hoặc Bcrypt.
   - **Quản lý bí mật**: Lưu trữ toàn bộ API Keys trong tệp `.env` không commit lên Git.
