#!/bin/bash

# YomuTomo 部署脚本
# 用于自动化部署到服务器

set -e

echo "🚀 YomuTomo 部署脚本"
echo "========================"

# 检查环境变量
if [ -z "$OPENAI_API_KEY" ]; then
    echo "❌ 请设置 OPENAI_API_KEY 环境变量"
    exit 1
fi

# 生成随机密钥
if [ -z "$SECRET_KEY" ]; then
    SECRET_KEY=$(openssl rand -hex 32)
    echo "🔑 生成随机 SECRET_KEY: $SECRET_KEY"
    export SECRET_KEY
fi

# 生成随机数据库密码
if [ -z "$POSTGRES_PASSWORD" ]; then
    POSTGRES_PASSWORD=$(openssl rand -hex 16)
    echo "🔒 生成随机数据库密码: $POSTGRES_PASSWORD"
    export POSTGRES_PASSWORD
fi

echo "📦 构建 Docker 镜像..."
docker-compose build

echo "🗃️ 启动 PostgreSQL..."
docker-compose up -d postgres

echo "⏳ 等待数据库就绪..."
sleep 10

echo "🚀 启动应用..."
docker-compose up -d yomu_app

echo "✅ 部署完成！"
echo ""
echo "📊 服务状态："
docker-compose ps

echo ""
echo "🌐 应用访问地址：http://localhost:8000"
echo "📖 API 文档：http://localhost:8000/docs"
echo ""
echo "🔧 管理命令："
echo "  查看日志：docker-compose logs -f"
echo "  停止服务：docker-compose down"
echo "  重启服务：docker-compose restart"
echo ""
echo "💾 数据库信息："
echo "  主机：localhost:5432"
echo "  数据库：yomu_pg"
echo "  用户：postgres"
echo "  密码：$POSTGRES_PASSWORD"
