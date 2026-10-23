# feature/doc-viewer

## 目的

为知识库页面（KnowledgeBasePage）补齐**文档内容查看**能力 — 上传后的资料之前无法在 Web 前端查看原文内容，现在可通过 API 拉取并在线浏览。

## 后端变更

### 新增 API（`backend/app/api/routes/sources.py`）

| 方法 | 路径 | 用途 |
|------|------|------|
| GET | `/api/v1/projects/{project_id}/sources` | 列出项目下所有资料（含快照引用标记） |
| GET | `/api/v1/projects/{project_id}/sources/{source_id}` | 读取资料原文内容 |
| GET | `/api/v1/projects/{project_id}/sources/{source_id}/chunks` | 列出资料解析后的分段 |

原有 POST 上传接口不变。

### 新增服务函数（`backend/app/application/services/source_service.py`）

- `list_project_sources()` — 查询项目所有 SourceRevision，标记哪些已被快照引用
- `read_source_content()` — 通过 LocalArtifactStorage 读取原文
- `list_source_chunks()` — 查询 DocumentChunk 分段列表

### 新增 Schema（`backend/app/api/schemas.py`）

- `SourceDetailResponse` — 列表项（含 source_role、in_snapshot、时间戳）
- `SourceContentResponse` — 原文内容（content + media_type + logical_name）
- `ChunkItemResponse` — 分段信息（chunk_index + locator + index_version）

## 前端变更

### `frontend/src/pages/KnowledgeBasePage.vue`

- 移除硬编码的 fixtures 数据，改为通过 fetch 调用后端 API
- 页面顶部新增项目 UUID 输入框 + 加载按钮（UUID 持久化到 sessionStorage）
- 文档表格行可点击，弹出原文查看浮层（Teleport 到 body）
- 类型筛选侧栏根据实际数据动态生成选项
- 表格列：文档名称 / 类型 / 版本 / 处理状态 / 快照引用 / 更新时间

### `frontend/src/styles.css`

- 知识库表格列宽从 8 列调整为 6 列
- 新增 `.kb-project-input`、`.kb-project-row` 输入区样式
- 新增 `.content-overlay`、`.content-modal`、`.content-modal-header`、`.content-modal-body` 查看器样式
