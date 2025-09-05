-- 初始化脚本（可选）
-- FastAPI应用会在启动时自动创建表结构
-- 这个文件可以用来添加初始数据或额外的数据库配置

-- 示例：创建索引以提升查询性能
-- CREATE INDEX IF NOT EXISTS idx_articles_user_id ON articles(user_id);
-- CREATE INDEX IF NOT EXISTS idx_articles_updated_at ON articles(updated_at DESC);

-- 示例：添加初始管理员用户（可选）
-- INSERT INTO users (email, password_hash, created_at)
-- VALUES ('admin@example.com', '$2b$12$...', NOW())
-- ON CONFLICT (email) DO NOTHING;
