# 多格式项目知识库设计

## 目标与边界

项目知识库接收并管理项目证据知识的不可变版本。它以浏览、分类、版本、来源定位和快照引用为中心；文件导入只是知识进入系统的次级入口。Notebook 只能选择处理完成的 `READY` 知识版本。

首期支持 TXT、Markdown、CSV、JSON、YAML、XML、HTML、DOC/DOCX、XLS/XLSX、PPT/PPTX、ODT/ODS/ODP、PDF、PNG/JPEG/WEBP/TIFF。它不接收音视频、压缩包、加密文件或受密码保护的 Office/PDF；不执行宏、脚本、嵌入对象或外部链接。

## 导入生命周期

上传创建不可变 `SourceRevision`，保存原文件及内容哈希。派生提取结果保存规范文本、解析器版本、OCR 统计、失败码和提取元数据。旧快照不会因重新解析或升级解析器被改写。

`UPLOADED → PARSING → OCR_CHECKING（按需）→ CHUNKING → INDEXING → READY`

不支持、加密、格式损坏、转换失败、OCR 低置信度或提取为空时进入 `FAILED`，保留原文件与可追溯错误。默认限制为单文件 100 MiB、PDF 500 页，可由服务端配置覆盖。OCR 的总体置信度须不低于 85%，任一有效文字页不得低于 60%，否则不得进入 `READY`。

## 解析和定位

格式检测综合文件签名、MIME 和扩展名。纯文本及结构化文本使用本地解析器；现代 Office 使用专用 Python 提取器；旧 Office 和 ODF 使用 LibreOffice 无界面转换；PDF 优先读取文字层，文字不足时逐页 OCR；图片直接 OCR。Tesseract 使用中文简体与英文语言包。

全部解析器输出统一文本片段和精确 `locator`：PDF 页码/字符范围或 OCR 区域，Word 段落/表格，Excel 工作表/单元格范围，PPT 幻灯片/文本框，结构化文本的路径或行范围，图片 OCR 区域。`DocumentChunk` 与 `EvidenceItem` 沿用既有回链和不可变快照语义。

## 后端与接口

导入在 Worker 中异步执行，避免 OCR 和 Office 转换阻塞上传请求。`POST /projects/{projectId}/sources` 接受受控 multipart 文件；资料列表和详情增加媒体类型、处理阶段、提取统计、OCR 置信度、失败码、原文件下载及规范文本/定位查询。不会提供任意执行、宏执行、压缩包解压或外部 URL 抓取接口。

## 前端

项目知识库保留资料分类、版本、状态、原文/提取文本和快照引用的主信息结构；“导入知识”使用折叠或次级入口。资料卡片展示格式、提取进度、OCR 状态和失败建议。阅读视图可按页、幻灯片、工作表或 OCR 区域定位证据。Notebook 保持只选择 `READY` 资料版本。

## 验证

为每类格式、伪装媒体类型、加密文件、转换失败、OCR 阈值、资料状态门禁和证据定位增加定向用例。完成后使用 `D:\测试文档\省民政厅测试文档\查重测试文档` 的真实文档进行导入、处理、知识预览和 READY/FAILED 门禁验证。
