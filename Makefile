# YomuTomo - 开发和部署工具

.PHONY: help install dev build up down logs clean

# 默认目标
help: ## 显示帮助信息
	@echo "YomuTomo - 日语朗读应用"
	@echo ""
	@echo "开发命令:"
	@echo "  make install    安装依赖"
	@echo "  make dev        启动开发服务器"
	@echo "  make build      构建Docker镜像"
	@echo "  make up         启动Docker服务"
	@echo "  make down       停止Docker服务"
	@echo "  make logs       查看日志"
	@echo "  make clean      清理Docker资源"
	@echo ""
	@echo "部署命令:"
	@echo "  make deploy     生产环境部署"
	@echo "  make backup     备份数据库"
	@echo ""

install: ## 安装Python依赖
	pip install -r requirements.txt

dev: ## 启动开发服务器
	python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000

build: ## 构建Docker镜像
	docker build -t yomu-app .

up: ## 启动Docker服务（开发环境）
	docker-compose up -d

down: ## 停止Docker服务
	docker-compose down

logs: ## 查看Docker日志
	docker-compose logs -f

clean: ## 清理Docker资源
	docker-compose down -v
	docker system prune -f
	docker volume rm yomu_postgres_data || true

deploy: ## 生产环境部署
	docker-compose -f docker-compose.prod.yml up -d

backup: ## 备份数据库
	@echo "备份数据库..."
	docker exec yomu_postgres pg_dump -U postgres yomu_pg > backup_$(shell date +%Y%m%d_%H%M%S).sql
	@echo "备份完成"

restore: ## 恢复数据库（需要指定备份文件）
	@echo "恢复数据库..."
	@if [ -z "$(file)" ]; then \
		echo "请指定备份文件: make restore file=backup_file.sql"; \
		exit 1; \
	fi
	docker exec -i yomu_postgres psql -U postgres yomu_pg < $(file)
	@echo "恢复完成"

test: ## 运行测试
	pytest

lint: ## 代码检查
	flake8 app/
	black --check app/
	isort --check-only app/

format: ## 格式化代码
	black app/
	isort app/

# 生产环境管理
prod-up: ## 启动生产环境
	docker-compose -f docker-compose.prod.yml up -d

prod-down: ## 停止生产环境
	docker-compose -f docker-compose.prod.yml down

prod-logs: ## 查看生产环境日志
	docker-compose -f docker-compose.prod.yml logs -f

prod-nginx: ## 启动生产环境（包含Nginx）
	docker-compose -f docker-compose.prod.yml --profile nginx up -d
