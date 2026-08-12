# Shared

保留目录:预留给跨包共享的 schema / 类型定义(例如前后端共用的 JSON schema)。

当前各包 schema 分别维护于 `backend/app/schemas/` 与 `frontend/lib/types.ts`;若后续出现需要前后端共享的定义,再收敛到此目录。